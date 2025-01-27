"""
This module needs extra-dependencies not installed as core dependencies of medkit.
To install them, use `pip install medkit-lib[umls-coder-normalizer]`.
"""

__all__ = ["UMLSCoderNormalizer"]

from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union
from typing_extensions import Literal
from pathlib import Path

import pandas as pd
import torch
import transformers
from transformers import PreTrainedModel, PreTrainedTokenizer, FeatureExtractionPipeline
import yaml

from medkit.core import Operation
from medkit.core.text import Entity
import medkit.core.utils
from medkit.text.ner.umls_norm_attribute import UMLSNormAttribute
from medkit.text.ner.umls_utils import (
    load_umls,
    preprocess_term_to_match,
    guess_umls_version,
)


_PARAMS_FILENAME = "params.yml"
_TERMS_FILENAME = "terms.feather"
_UMLS_EMBEDDINGS_CHUNK_SIZE = 65536
_UMLS_EMBEDDINGS_FILE_EXT = ".pt"


class _UMLSEmbeddingsParams(NamedTuple):
    umls_version: str
    language: str
    model: str
    summary_method: Literal["mean", "cls"]
    normalize_embeddings: bool
    lowercase: bool
    normalize_unicode: bool

    def to_dict(self) -> Dict[str, Any]:
        return dict(
            umls_version=self.umls_version,
            language=self.language,
            model=self.model,
            summary_method=self.summary_method,
            normalize_embeddings=self.normalize_embeddings,
            lowercase=self.lowercase,
            normalize_unicode=self.normalize_unicode,
        )


class UMLSCoderNormalizer(Operation):
    """Normalizer adding UMLS normalization attributes to
    pre-existing entities. Based on https://github.com/GanjinZero/CODER/.

    An UMLS `MRCONSO.RRF` file is needed. The normalizer identifies UMLS concepts by
    comparing embeddings of reference UMLS terms with the embeddings of the input
    entities. Any text transformer model from the HuggingFace Hub can be used,
    but "GanjinZero/UMLSBert_ENG" was specifically trained for this task (for english).

    When `UMLSCoderNormalizer` is used for the first time for a given `MRCONSO.RRF`,
    the embeddings of all umls terms are pre-computed (this can take a very long time)
    and stored in `embeddings_cache_dir`, so they can be reused next time.

    If another `MRCONSO.RRF` file is used, or if a parameter impacting the computation
    of embeddings (`model`, `summary_method`, etc) is changed, then another `embeddings_cache_dir`
    must be used, or `embeddings_cache_dir` must be deleted so it can be created properly.

    If the umls embeddings are too big to be held in memory, use `nb_umls_embeddings_chunks`.
    """

    def __init__(
        self,
        umls_mrconso_file: Union[str, Path],
        language: str,
        model: Union[str, Path],
        embeddings_cache_dir: Union[str, Path],
        summary_method: Literal["mean", "cls"] = "cls",
        normalize_embeddings: bool = True,
        lowercase: bool = False,
        normalize_unicode: bool = False,
        threshold: Optional[float] = None,
        max_nb_matches: int = 1,
        device: int = -1,
        batch_size: int = 128,
        nb_umls_embeddings_chunks: Optional[int] = None,
        hf_cache_dir: Optional[Union[str, Path]] = None,
        name: Optional[str] = None,
        uid: Optional[str] = None,
    ):
        """
        Parameters
        ----------
        umls_mrconso_file:
            Path to the UMLS `MRCONSO.RRF` file.
        language:
            Language of the UMLS terms to use (ex: `"ENG"`, `"FRE"`).
        model:
            Name on the Hugging Face hub or path to the transformers model that will be used to extract
            embeddings (ex: `"GanjinZero/UMLSBert_ENG"`).
        embeddings_cache_dir:
            Path to the directory into which pre-computed embeddings of UMLS terms should be cached.
            If it doesn't exist yet, the embeddings will be automatically generated (it can take a long
            time) and stored there, ready to be reused on further instantiations.
            If it already exists, a check will be done to make sure the params used when the embeddings
            were computed are consistent with the params of the current instance.
        summary_method:
            If set to `"mean"`, the embeddings extracted will be the mean of the pooling layers
            of the model. Otherwise, when set to `"cls"`, the last hidden layer will be used.
        normalize_embeddings:
            Whether to normalize the extracted embeddings.
        lowercase:
            Whether to use lowercased versions of UMLS terms and input entities.
        normalize_unicode:
            Whether to ASCII-only versions of UMLS terms and input entities
            (non-ASCII chars replaced by closest ASCII chars).
        threshold:
            Minimum similarity threshold (between 0.0 and 1.0) between the embeddings
            of an entity and of an UMLS term for a normalization attribute to be added.
        max_nb_matches:
            Maximum number of normalization attributes to add to each entity.
        device:
            Device to use for transformers models. Follows the Hugging Face convention
            (-1 for "cpu" and device number for gpu, for instance 0 for "cuda:0").
        batch_size:
            Number of entities in batches processed by the embeddings extraction pipeline.
        hf_cache_dir:
            Directory where to store downloaded models. If not set, the default
            HuggingFace cache dir is used.
        nb_umls_embeddings_chunks:
            Number of umls embeddings chunks to load at the same time when computing
            embeddings similarities. (a chunk contains 65536 embeddings).
            If `None`, all pre-computed umls embeddings are pre-loaded in memory and
            similaries are computed in one shot. Otherwise, at each call to `run()`,
            umls embeddings are loaded by groups of chunks and similaries are computed
            for each group.
            Use this when umls embeddings are too big to be fully loaded in memory.
            The higher this value, the more memory needed.
        name:
            Name describing the normalizer (defaults to the class name).
        uid:
            Identifier of the normalizer.
        """
        # Pass all arguments to super (remove self)
        init_args = locals()
        init_args.pop("self")
        super().__init__(**init_args)

        self.umls_mrconso_file = Path(umls_mrconso_file)
        self.embeddings_cache_dir = Path(embeddings_cache_dir)
        self.language = language
        self.model = model
        self.summary_method = summary_method
        self.normalize_embeddings = normalize_embeddings
        self.lowercase = lowercase
        self.normalize_unicode = normalize_unicode
        self.threshold = threshold
        self.max_nb_matches = max_nb_matches
        self.device = device
        self.nb_umls_embeddings_chunks = nb_umls_embeddings_chunks

        self._pipeline: _EmbeddingsPipeline = transformers.pipeline(
            "feature-extraction",
            model=self.model,
            pipeline_class=_EmbeddingsPipeline,
            summary_method=summary_method,
            normalize=normalize_embeddings,
            device=device,
            batch_size=batch_size,
            model_kwargs={"cache_dir": hf_cache_dir},
        )

        # guess UMLS version
        self._umls_version = guess_umls_version(umls_mrconso_file)

        # pre-compute embeddings of UMLS terms if necessary
        self._build_umls_embeddings()

        # preload all pre-computed UMLS embeddings if nb_umls_embeddings_chunks not set
        if self.nb_umls_embeddings_chunks is None:
            umls_embeddings_files = sorted(
                self.embeddings_cache_dir.glob(f"*{_UMLS_EMBEDDINGS_FILE_EXT}")
            )
            self._umls_embeddings = self._load_umls_embeddings(umls_embeddings_files)
        else:
            self._umls_embeddings = None

        # load corresponding UMLS terms and associated CUIs
        umls_terms_file = self.embeddings_cache_dir / _TERMS_FILENAME
        self._umls_entries = pd.read_feather(umls_terms_file)

    def run(self, entities: List[Entity]):
        """Add normalization attributes to each entity in `entities`.

        Each entity will have zero, one or more normalization attributes depending
        on `max_nb_matches` and on how many matches with a similarity above `threshold`
        are found.

        Parameters
        ----------
        entities:
            List of entities to add normalization attributes to
        """

        # find best matches and assocatied score for all entities
        all_match_indices, all_match_scores = self._find_best_matches(entities)

        # add normalization attributes to each entity
        for entity, match_indices, match_scores in zip(
            entities, all_match_indices, all_match_scores
        ):
            self._normalize_entity(entity, match_indices, match_scores)

    def _find_best_matches(
        self, entities: List[Entity]
    ) -> Tuple[List[List[int]], List[List[float]]]:
        entity_terms = [entity.text for entity in entities]
        entity_embeddings = self._pipeline(entity_terms)
        entity_embeddings = torch.cat(entity_embeddings, dim=0)

        if self.nb_umls_embeddings_chunks is not None:
            # compute similarities for each batch of pre-computed umls embeddings
            all_similarities = []
            umls_embeddings_files = sorted(
                self.embeddings_cache_dir.glob(f"*{_UMLS_EMBEDDINGS_FILE_EXT}")
            )
            for files in medkit.core.utils.batch_list(
                umls_embeddings_files, self.nb_umls_embeddings_chunks
            ):
                umls_embeddings = self._load_umls_embeddings(files)
                all_similarities.append(
                    torch.matmul(entity_embeddings, umls_embeddings.T)
                )
            similarities = torch.cat(all_similarities, dim=1)
        else:
            # compute similarity on all pre-loaded pre-computed umls embeddings
            assert self._umls_embeddings is not None
            similarities = torch.matmul(entity_embeddings, self._umls_embeddings.T)

        all_matches_scores, all_matches_indices = torch.topk(
            similarities, k=self.max_nb_matches
        )
        # round scores to avoid floating point precision errors and get
        # 1.0 for exact matches instead of values slightly above or below
        all_matches_scores = torch.round(all_matches_scores, decimals=4)
        return all_matches_indices.tolist(), all_matches_scores.tolist()

    def _load_umls_embeddings(self, files: List[Path]) -> torch.Tensor:
        torch_device = "cpu" if self.device < 0 else f"cuda:{self.device}"
        umls_embeddings = torch.cat(
            [torch.load(file, map_location=torch_device) for file in files]
        )
        return umls_embeddings

    def _normalize_entity(
        self, entity: Entity, match_indices: List[int], match_scores: List[float]
    ):
        for match_index, match_score in zip(match_indices, match_scores):
            if self.threshold is not None and match_score < self.threshold:
                continue

            umls_entry = self._umls_entries.iloc[match_index]
            norm_attr = UMLSNormAttribute(
                cui=umls_entry.cui,
                umls_version=self._umls_version,
                term=umls_entry.term,
                score=match_score,
            )
            entity.attrs.add(norm_attr)

            if self._prov_tracer is not None:
                self._prov_tracer.add_prov(
                    norm_attr, self.description, source_data_items=[entity]
                )

    def _build_umls_embeddings(self, show_progress=True):
        # build description of computation params
        params = _UMLSEmbeddingsParams(
            umls_version=self._umls_version,
            language=self.language,
            model=self.model,
            summary_method=self.summary_method,
            normalize_embeddings=self.normalize_embeddings,
            lowercase=self.lowercase,
            normalize_unicode=self.normalize_unicode,
        )

        # check if embeddings have already been computed
        params_file = self.embeddings_cache_dir / _PARAMS_FILENAME
        if params_file.exists():
            # check consistency of params
            with open(params_file) as fp:
                existing_params = _UMLSEmbeddingsParams(**yaml.safe_load(fp))
            if existing_params != params:
                raise Exception(
                    f"Cache directory {self.embeddings_cache_dir} contains UMLS"
                    f" embeddings pre-computed with different params: {params} vs"
                    f" {existing_params}"
                )

            # nothing to do, embeddings have already been computed
            return

        if show_progress:
            print(
                "No pre-existing UMLS embeddings found in cache directory"
                f" {self.embeddings_cache_dir}, pre-computing them right now"
            )

        self.embeddings_cache_dir.mkdir(exist_ok=True)

        # remove all previous embedding files for safety
        [
            f.unlink()
            for f in self.embeddings_cache_dir.glob(f"*{_UMLS_EMBEDDINGS_FILE_EXT}")
        ]

        # get iterator to all UMLS entries
        entries_iter = load_umls(
            self.umls_mrconso_file,
            languages=[self.language],
            show_progress=show_progress,
        )

        entries_by_term_to_match = {}
        # iterate over chunks of umls entries
        if show_progress:
            print("Loading UMLS entries and computing embeddings...")
        for i, chunk_entries in enumerate(
            medkit.core.utils.batch_iter(entries_iter, _UMLS_EMBEDDINGS_CHUNK_SIZE)
        ):
            # get preprocess version of each term for matching
            terms_to_match = [
                preprocess_term_to_match(e.term, self.lowercase, self.normalize_unicode)
                for e in chunk_entries
            ]

            # skip entry with duplicate terms to match
            chunk_entries_by_term_to_match = {
                term_to_match: entry
                for term_to_match, entry in zip(terms_to_match, chunk_entries)
                if term_to_match not in entries_by_term_to_match
            }
            if not chunk_entries_by_term_to_match:
                continue
            entries_by_term_to_match.update(chunk_entries_by_term_to_match)

            # compute embedding for each term
            chunk_embeddings_iter = self._pipeline(
                term_to_match for term_to_match in chunk_entries_by_term_to_match
            )
            chunk_embeddings = torch.cat(list(chunk_embeddings_iter), dim=0)
            chunk_embeddings_file = (
                self.embeddings_cache_dir / f"{i:010d}{_UMLS_EMBEDDINGS_FILE_EXT}"
            )
            # save chunk embeddings
            torch.save(chunk_embeddings, chunk_embeddings_file)

        # store entries in feather file (faster than csv and yaml)
        entries_df = pd.DataFrame.from_records(
            [e.to_dict() for e in entries_by_term_to_match.values()]
        )
        terms_file = self.embeddings_cache_dir / _TERMS_FILENAME
        if show_progress:
            print("Writing UMLS terms... ", end="")
        entries_df.to_feather(terms_file)
        if show_progress:
            print("Done")

        # store params into yaml
        with open(params_file, mode="w") as fp:
            yaml.safe_dump(
                params.to_dict(),
                fp,
                encoding="utf-8",
                allow_unicode=True,
                sort_keys=False,
            )


class _EmbeddingsPipeline(FeatureExtractionPipeline):
    """Extract embeddings from a pipeline"""

    _EPS = 1e-12

    def __init__(
        self,
        model: PreTrainedModel,
        tokenizer: PreTrainedTokenizer,
        summary_method: Literal["mean", "cls"],
        normalize: bool = True,
        *args,
        **kwargs,
    ):
        super().__init__(model, tokenizer, *args, **kwargs)

        self.summary_method = summary_method
        self.normalize = normalize

    def preprocess(self, inputs, truncation=True) -> Dict[str, torch.Tensor]:
        return self.tokenizer(
            inputs,
            max_length=32,
            add_special_tokens=True,
            truncation=truncation,
            padding="max_length",
            return_tensors="pt",
        )

    def postprocess(self, model_outputs) -> torch.Tensor:
        if self.summary_method == "cls":
            embeddings = model_outputs[1]
        else:
            assert self.summary_method == "mean"
            embeddings = torch.mean(model_outputs[0], dim=1)
        if self.normalize:
            norm = torch.norm(embeddings, p=2, dim=1, keepdim=True).clamp(min=self._EPS)
            embeddings = embeddings / norm
        return embeddings
