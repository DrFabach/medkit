import pytest
import spacy
from spacy.tokens import Span as SpacySpan, Doc
from medkit.core import ProvBuilder
from medkit.core.text import Span, Entity, Segment
from medkit.text.spacy import SpacyPipeline


@spacy.Language.component(
    "_attribute_adder_v2",
    requires=["doc.ents"],
    retokenizes=False,
)
def _custom_component(spacy_doc: Doc) -> Doc:
    """Mock spacy component, this component adds two entities including 'has_numbers' as extension
    """
    # set an attribute in spacy
    if not SpacySpan.has_extension("has_numbers"):
        SpacySpan.set_extension("has_numbers", default=None)
    # add entities in spacy doc
    ents = [spacy_doc.char_span(0, 12, "PERSON"), spacy_doc.char_span(58, 62, "DATE")]
    spacy_doc.ents = list(spacy_doc.ents) + ents

    for ent in spacy_doc.ents:
        # modify the value of the attr
        value = any(token.is_digit for token in ent)
        ent._.set("has_numbers", value)
    return spacy_doc


@pytest.fixture(scope="module")
def nlp_spacy_modified():
    # use an empty spacy nlp object
    nlp = spacy.blank("en")
    nlp.add_pipe("_attribute_adder_v2", last=True)
    return nlp


TEXT_SPACY = "Marie Dupont started treatment at the central hospital in 2012"


def _get_segment():
    return Segment(text=TEXT_SPACY, spans=[Span(0, len(TEXT_SPACY))], label="test")


def test_default_spacy_pipeline(nlp_spacy_modified):
    # by default, spacyPipeline converts all spacy entities and spans
    # to medkit entities and segments
    segment = _get_segment()
    pipe = SpacyPipeline(nlp_spacy_modified)
    new_segments = pipe.run([segment])

    # original segment does not have entities, nlp from spacy adds 2 entities
    assert len(new_segments) == 2
    assert all(isinstance(seg, Entity) for seg in new_segments)
    assert all(len(seg.attrs) == 1 for seg in new_segments)

    ent = new_segments[0]
    assert ent.label == "PERSON"
    assert ent.text == "Marie Dupont"
    assert ent.attrs[0].label == "has_numbers"
    assert not ent.attrs[0].value

    ent = new_segments[1]
    assert ent.label == "DATE"
    assert ent.text == "2012"
    assert ent.attrs[0].label == "has_numbers"
    assert ent.attrs[0].value


def test_prov(nlp_spacy_modified):
    prov_builder = ProvBuilder()

    segment = _get_segment()
    # set provenance builder
    pipe = SpacyPipeline(nlp=nlp_spacy_modified)
    pipe.set_prov_builder(prov_builder)

    # execute the pipeline
    new_segments = pipe.run([segment])

    graph = prov_builder.graph

    # check new entity
    entity = new_segments[0]
    node = graph.get_node(entity.id)
    assert node.data_item_id == entity.id
    assert node.operation_id == pipe.id
    assert node.source_ids == [segment.id]

    attribute = entity.attrs[0]
    attr = graph.get_node(attribute.id)
    assert attr.data_item_id == attribute.id
    assert attr.operation_id == pipe.id
    assert attr.source_ids == [segment.id]