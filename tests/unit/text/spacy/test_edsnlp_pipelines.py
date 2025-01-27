import pytest

spacy = pytest.importorskip(modname="spacy", reason="spacy is not installed")
_ = pytest.importorskip(modname="edsnlp", reason="edsnlp is not installed")


from spacy.tokens.underscore import Underscore

from medkit.core import Attribute
from medkit.core.text import TextDocument, Entity, Segment, Span
from medkit.text.ner import (
    DateAttribute,
    RelativeDateAttribute,
    RelativeDateDirection,
    DurationAttribute,
    ADICAPNormAttribute,
)
from medkit.text.ner.tnm_attribute import TNMAttribute
from medkit.text.spacy.edsnlp import EDSNLPPipeline, EDSNLPDocPipeline


def _get_segment(text):
    return Segment(label="sentence", text=text, spans=[Span(0, len(text))])


@pytest.fixture(scope="function", autouse=True)
def reset_spacy_extensions():
    yield
    Underscore.doc_extensions = {}
    Underscore.span_extensions = {}
    Underscore.token_extensions = {}


def test_dates_pipeline():
    nlp = spacy.blank("eds")
    nlp.add_pipe("eds.dates")
    edsnlp_pipeline = EDSNLPPipeline(nlp)

    # absolute date
    seg = _get_segment("Hospitalisé le 25/10/2012")
    anns = edsnlp_pipeline.run([seg])

    assert len(anns) == 1
    date_seg = anns[0]
    assert isinstance(date_seg, Segment)
    assert date_seg.text == "25/10/2012"

    date_attrs = date_seg.attrs.get(label="date")
    assert len(date_attrs) == 1
    date_attr = date_attrs[0]
    assert isinstance(date_attr, DateAttribute)
    assert date_attr.year == 2012 and date_attr.month == 10 and date_attr.day == 25

    # relative date
    seg = _get_segment("Hospitalisé il y a 2 mois")
    anns = edsnlp_pipeline.run([seg])

    assert len(anns) == 1
    date_seg = anns[0]
    assert date_seg.text == "il y a 2 mois"

    date_attrs = date_seg.attrs.get(label="date")
    assert len(date_attrs) == 1
    date_attr = date_attrs[0]
    assert isinstance(date_attr, RelativeDateAttribute)
    assert date_attr.direction == RelativeDateDirection.PAST
    assert date_attr.months == 2

    # duration
    seg = _get_segment("Hospitalisé pendant 2 mois")
    anns = edsnlp_pipeline.run([seg])

    assert len(anns) == 1
    date_seg = anns[0]
    assert date_seg.text == "pendant 2 mois"

    date_attrs = date_seg.attrs.get(label="date")
    assert len(date_attrs) == 1
    date_attr = date_attrs[0]
    assert isinstance(date_attr, DurationAttribute)
    assert date_attr.months == 2


def test_adicap_pipeline():
    seg = _get_segment("Codification: BHGS0040")

    nlp = spacy.blank("eds")
    nlp.add_pipe("eds.sentences")
    nlp.add_pipe("eds.adicap")
    edsnlp_pipeline = EDSNLPPipeline(nlp)
    anns = edsnlp_pipeline.run([seg])

    assert len(anns) == 1
    entity = anns[0]
    assert isinstance(entity, Entity)
    assert entity.text == "BHGS0040"

    norm_attrs = entity.attrs.norms
    assert len(norm_attrs) == 1
    adicap_attr = norm_attrs[0]
    assert isinstance(adicap_attr, ADICAPNormAttribute)
    assert adicap_attr.sampling_mode == "BIOPSIE CHIRURGICALE"


def test_tnm_pipeline():
    seg = _get_segment("TNM: pTx N1 M1")

    nlp = spacy.blank("eds")
    nlp.add_pipe("eds.TNM")
    edsnlp_pipeline = EDSNLPPipeline(nlp)
    anns = edsnlp_pipeline.run([seg])

    assert len(anns) == 1
    entity = anns[0]
    assert isinstance(entity, Entity)
    assert entity.text == "pTx N1 M1"

    tnm_attrs = entity.attrs.get(label="TNM")
    assert len(tnm_attrs) == 1
    tnm_attr = tnm_attrs[0]
    assert isinstance(tnm_attr, TNMAttribute)
    assert tnm_attr.tumour_specification.value == "x"


def test_family_pipeline():
    seg = _get_segment("Suspicion de tumeur maligne. antécédents familiaux de cancer")

    nlp = spacy.blank("eds")
    nlp.add_pipe("eds.sentences")
    nlp.add_pipe("eds.matcher", config=dict(terms={"problem": ["cancer", "tumeur"]}))
    nlp.add_pipe("eds.family")
    edsnlp_pipeline = EDSNLPPipeline(nlp)
    anns = edsnlp_pipeline.run([seg])

    assert len(anns) == 2
    entity_1 = anns[0]
    assert entity_1.label == "problem"
    assert entity_1.text == "tumeur"
    family_attrs_1 = entity_1.attrs.get(label="family")
    assert len(family_attrs_1) == 1 and family_attrs_1[0].value is False

    entity_2 = anns[1]
    assert entity_2.text == "cancer"
    family_attrs_2 = entity_2.attrs.get(label="family")
    assert len(family_attrs_2) == 1 and family_attrs_2[0].value is True


def test_custom_attribute_factory():
    """
    Use a custom attribute factory overriding one of the default attribute
    factories
    """

    def build_date_attribute(span, label):
        return Attribute(label="date", value=span._.get(label).norm())

    nlp = spacy.blank("eds")
    nlp.add_pipe("eds.dates")
    edsnlp_pipeline = EDSNLPPipeline(
        nlp, medkit_attribute_factories={"date": build_date_attribute}
    )

    seg = _get_segment("Hospitalisé le 25/10/2012")
    anns = edsnlp_pipeline.run([seg])
    date_seg = anns[0]
    date_attr = date_seg.attrs.get(label="date")[0]
    assert type(date_attr) is Attribute and date_attr.value == "2012-10-25"


def test_doc_pipeline():
    doc = TextDocument("Hospitalisé le 25/10/2012 pour tumeur maligne potentielle")

    nlp = spacy.blank("eds")
    nlp.add_pipe("eds.sentences")
    nlp.add_pipe("eds.matcher", config=dict(terms={"problem": ["tumeur"]}))
    nlp.add_pipe("eds.hypothesis")
    nlp.add_pipe("eds.dates")

    edsnlp_pipeline = EDSNLPDocPipeline(nlp)
    edsnlp_pipeline.run([doc])

    entities = doc.anns.entities
    assert len(entities) == 1
    entity = entities[0]
    assert entity.label == "problem"
    assert entity.text == "tumeur"
    entity_attrs = list(entity.attrs)
    assert len(entity_attrs) == 1
    entity_attr = entity_attrs[0]
    assert entity_attr.label == "hypothesis" and entity_attr.value is True

    segs = doc.anns.segments
    assert len(segs) == 1
    date_seg = segs[0]
    assert date_seg.label == "dates"
    assert date_seg.text == "25/10/2012"
    date_attrs = date_seg.attrs.get(label="date")
    assert len(date_attrs) == 1
    entity_attr = date_attrs[0]
    assert isinstance(entity_attr, DateAttribute) and entity_attr.year == 2012
