import pytest
from medkit.core.prov_builder import ProvBuilder

from medkit.core.text import Span, ModifiedSpan, Segment
from medkit.text.preprocessing.eds_cleaner import EDSCleaner

TEST_DEFAULT_CONFIG = [
    (
        "Nom patient : la Mme. Marie Dupont, date le     .24 avril .    pour un"
        " probleme",
        "Nom patient : la Mme  Marie Dupont, date le 24 avril pour un probleme",
        [
            Span(start=0, end=20),
            ModifiedSpan(length=1, replaced_spans=[Span(start=20, end=21)]),
            Span(start=21, end=43),
            ModifiedSpan(length=1, replaced_spans=[Span(start=43, end=49)]),
            Span(start=49, end=57),
            ModifiedSpan(length=1, replaced_spans=[Span(start=57, end=63)]),
            Span(start=63, end=79),
        ],
    ),
    (
        "Traitement : (N.B. : absence de notion de la prescription d'une HBPM)\n\n\n à"
        " dose curative dès cet appel.",
        "Traitement : à dose curative dès cet appel ; N B. : absence de notion de la"
        " prescription d'une HBPM.",
        [
            Span(start=0, end=12),
            ModifiedSpan(length=1, replaced_spans=[]),
            Span(start=73, end=102),
            ModifiedSpan(length=3, replaced_spans=[]),
            Span(start=14, end=15),
            ModifiedSpan(length=1, replaced_spans=[Span(start=15, end=16)]),
            Span(start=16, end=68),
            ModifiedSpan(length=1, replaced_spans=[]),
        ],
    ),
    (
        "Résultats : examen reviens (+) le (5 juin)",
        "Résultats : examen reviens  positif  le ,5 juin,",
        [
            Span(start=0, end=27),
            ModifiedSpan(length=9, replaced_spans=[Span(start=27, end=30)]),
            Span(start=30, end=34),
            ModifiedSpan(length=1, replaced_spans=[Span(start=34, end=35)]),
            Span(start=35, end=41),
            ModifiedSpan(length=1, replaced_spans=[Span(start=41, end=42)]),
        ],
    ),
    (
        "Le patient\n\n\n       reviens\n\n le 4 d\n\n\n\navril",
        "Le patient reviens le 4 d avril",
        [
            Span(start=0, end=10),
            ModifiedSpan(length=1, replaced_spans=[Span(start=10, end=20)]),
            Span(start=20, end=27),
            ModifiedSpan(length=1, replaced_spans=[Span(start=27, end=30)]),
            Span(start=30, end=36),
            ModifiedSpan(length=1, replaced_spans=[Span(start=36, end=40)]),
            Span(start=40, end=45),
        ],
    ),
]


def _get_raw_segment(text):
    return Segment(
        label="RAW_TEXT",
        spans=[Span(0, len(text))],
        text=text,
    )


@pytest.mark.parametrize(
    "text,expected_text,expected_spans",
    TEST_DEFAULT_CONFIG,
    ids=[
        "replace_points_keywords_fr",
        "replace_large_parentheses",
        "replace_small_parentheses",
        "remove_multiple_newlines",
    ],
)
def test_default_cleaner(text, expected_text, expected_spans):
    # default config: this configuration allows to obtain the
    # same results as in the original version of the endlines function
    cleaner = EDSCleaner(
        keep_endlines=False, handle_parentheses_eds=True, handle_points_eds=True
    )
    raw_segment = _get_raw_segment(text)
    clean_ann = cleaner.run([raw_segment])[0]
    assert clean_ann.text == expected_text
    assert clean_ann.spans == expected_spans


TEST_PARAMS_CONFIG = [
    (
        EDSCleaner(keep_endlines=True),
        "Le patient\n\n\n       reviens. Nom patient"
        " probleme.\n\nTraitement :\n\n\n à dose curative dès cet appel.",
        "Le patient reviens. Nom patient probleme..\nTraitement : à dose"
        " curative dès cet appel.",
        [
            Span(start=0, end=10),
            ModifiedSpan(length=1, replaced_spans=[Span(start=10, end=20)]),
            Span(start=20, end=50),
            ModifiedSpan(length=2, replaced_spans=[Span(start=50, end=52)]),
            Span(start=52, end=64),
            ModifiedSpan(length=1, replaced_spans=[Span(start=64, end=68)]),
            Span(start=68, end=98),
        ],
    ),
    (
        EDSCleaner(keep_endlines=False),
        "Le patient\n\n\n       reviens. Nom patient"
        " probleme.\n\nTraitement :\n\n\n à dose curative dès cet appel.",
        "Le patient reviens. Nom patient probleme.. Traitement : à dose curative dès"
        " cet appel.",
        [
            Span(start=0, end=10),
            ModifiedSpan(length=1, replaced_spans=[Span(start=10, end=20)]),
            Span(start=20, end=50),
            ModifiedSpan(length=2, replaced_spans=[Span(start=50, end=52)]),
            Span(start=52, end=64),
            ModifiedSpan(length=1, replaced_spans=[Span(start=64, end=68)]),
            Span(start=68, end=98),
        ],
    ),
    (
        EDSCleaner(handle_parentheses_eds=False),
        "Traitement : (N.B. : absence de notion de la prescription d'une HBPM)\n\n\n à"
        " dose curative dès cet appel.",
        "Traitement : (N B. : absence de notion de la prescription d'une HBPM) à dose"
        " curative dès cet appel.",
        [
            Span(start=0, end=15),
            ModifiedSpan(length=1, replaced_spans=[Span(start=15, end=16)]),
            Span(start=16, end=69),
            ModifiedSpan(length=1, replaced_spans=[Span(start=69, end=73)]),
            Span(start=73, end=103),
        ],
    ),
    (
        EDSCleaner(handle_points_eds=False),
        "Nom patient : la Mme. Marie Du  \n\npont, date le     .24 avril .    pour un"
        " probleme",
        "Nom patient : la Mme. Marie Du pont, date le     .24 avril .    pour un"
        " probleme",
        [
            Span(start=0, end=30),
            ModifiedSpan(length=1, replaced_spans=[Span(start=30, end=34)]),
            Span(start=34, end=83),
        ],
    ),
]


@pytest.mark.parametrize(
    "cleaner,text,expected_text,expected_spans",
    TEST_PARAMS_CONFIG,
    ids=[
        "keep_endlines_true",
        "keep_endlines_false",
        "no_change_parentheses_eds",
        "no_change_points_keywords_fr",
    ],
)
def test_cleaner_params(cleaner, text, expected_text, expected_spans):
    raw_segment = _get_raw_segment(text)
    clean_ann = cleaner.run([raw_segment])[0]
    assert clean_ann.text == expected_text
    assert clean_ann.spans == expected_spans


def test_prov():
    raw_segment = _get_raw_segment("Traitement :\n\n\n à dose curative dès cet appel.")

    cleaner = EDSCleaner()
    prov_builder = ProvBuilder()
    cleaner.set_prov_builder(prov_builder)
    clean_segments = cleaner.run([raw_segment])
    graph = prov_builder.graph

    clean_segment = clean_segments[0]
    node_1 = graph.get_node(clean_segment.id)
    assert node_1.data_item_id == clean_segment.id
    assert node_1.operation_id == cleaner.id
    assert node_1.source_ids == [raw_segment.id]