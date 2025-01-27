from pathlib import Path
import pytest

from medkit.core import Attribute
from medkit.core.text import (
    Entity,
    Relation,
    Segment,
    Span,
    ModifiedSpan,
    TextDocument,
    EntityNormAttribute,
)
from medkit.io._brat_utils import (
    BratAttribute,
    BratEntity,
    BratRelation,
    BratAnnConfiguration,
)
from medkit.io.brat import BratOutputConverter


def _get_medkit_doc():
    text = (
        "Le patient présente une douleur abdominale de grade 4, la douleur abdominale"
        " est sévère."
    )
    doc = TextDocument(uid="doc_brat", text=text)
    medkit_anns = [
        Entity(
            spans=[Span(24, 42)],
            label="maladie",
            text="douleur abdominale",
            uid="e1",
        ),
        Entity(
            spans=[Span(46, 53)],
            label="grade",
            text="grade 4",
            uid="e2",
            attrs=[Attribute("normalized", True)],
        ),
        Entity(
            spans=[Span(58, 76)],
            label="maladie",
            text="douleur abdominale",
            uid="e3",
        ),
        Entity(
            spans=[Span(81, 87)],
            label="level",
            text="sévère",
            uid="e4",
            attrs=[Attribute("normalized", False)],
        ),
        Relation(
            label="related",
            source_id="e1",
            target_id="e3",
            attrs=[Attribute("from_umls")],
            uid="r1",
        ),
        Segment(
            label="diagnosis",
            spans=[Span(0, 43), Span(81, 87)],
            text="Le patient présente une douleur abdominale sévère",
            uid="s1",
        ),
    ]
    for ann in medkit_anns:
        doc.anns.add(ann)

    return doc


TEST_DATA = [
    (
        None,
        None,
        False,
        False,
        """T1\tmaladie 24 42\tdouleur abdominale
T2\tgrade 46 53\tgrade 4
A1\tnormalized T2
T3\tmaladie 58 76\tdouleur abdominale
T4\tlevel 81 87\tsévère
T5\tdiagnosis 0 43;81 87\tLe patient présente une douleur abdominale sévère
R1\trelated Arg1:T1 Arg2:T3
A2\tfrom_umls R1
""",
    ),
    ([], [], False, False, ""),
    (
        ["maladie", "related"],
        ["from_umls"],
        False,
        False,
        """T1\tmaladie 24 42\tdouleur abdominale
T2\tmaladie 58 76\tdouleur abdominale
R1\trelated Arg1:T1 Arg2:T2
A1\tfrom_umls R1
""",
    ),
    (
        None,
        None,
        True,
        True,
        """T1\tmaladie 24 42\tdouleur abdominale
T2\tgrade 46 53\tgrade 4
A1\tnormalized T2
T3\tmaladie 58 76\tdouleur abdominale
T4\tlevel 81 87\tsévère
R1\trelated Arg1:T1 Arg2:T3
A2\tfrom_umls R1
""",
    ),
    ([], [], True, True, ""),
    (
        ["maladie", "related"],
        ["from_umls"],
        True,
        True,
        """T1\tmaladie 24 42\tdouleur abdominale
T2\tmaladie 58 76\tdouleur abdominale
R1\trelated Arg1:T1 Arg2:T2
A1\tfrom_umls R1
""",
    ),
]


@pytest.mark.parametrize(
    "ann_labels,attrs,ignore_segments,create_config,expected_ann",
    TEST_DATA,
    ids=[
        "all_anns_all_attrs",
        "no_anns_no_attrs",
        "list_anns_list_attrs",
        "all_anns_all_attrs_no_segment",
        "no_anns_no_attrs_no_segment",
        "list_anns_list_attrs_no_segment",
    ],
)
def test_save(
    tmp_path: Path, ann_labels, attrs, ignore_segments, create_config, expected_ann
):
    # create medkit_doc with 4 entities, 1 relation, 1 segment, 2 attrs
    medkit_doc = _get_medkit_doc()
    output_path = tmp_path / "output"
    expected_txt_path = output_path / f"{medkit_doc.uid}.txt"
    expected_ann_path = output_path / f"{medkit_doc.uid}.ann"
    expected_conf_path = output_path / "annotation.conf"

    # define a brat output converter all anns all attrs
    brat_converter = BratOutputConverter(
        anns_labels=ann_labels,
        ignore_segments=ignore_segments,
        create_config=create_config,
        attrs=attrs,
    )

    brat_converter.save([medkit_doc], output_path)

    assert output_path.exists()
    assert expected_txt_path.exists()
    assert expected_ann_path.exists()
    assert expected_txt_path.read_text() == medkit_doc.text
    assert expected_ann_path.read_text() == expected_ann
    if create_config:
        assert expected_conf_path.exists()
    else:
        assert not expected_conf_path.exists()


EXPECTED_CONFIG = """#Text-based definitions of entity types, relation types
#and attributes. This file was generated using medkit
#from the HeKa project
[entities]

grade
level
maladie
[relations]

# This line enables entity overlapping
<OVERLAP>\tArg1:<ENTITY>, Arg2:<ENTITY>, <OVL-TYPE>:<ANY>
related\tArg1:maladie, Arg2:maladie
[attributes]

normalized\tArg:<ENTITY>
from_umls\tArg:<RELATION>
[events]\n\n"""


def test_annotation_conf_file():
    # test to check configuration file
    # create medkit_doc with 4 entities, 1 relation, 1 segment, 2 attrs
    medkit_doc = _get_medkit_doc()

    brat_converter = BratOutputConverter(
        anns_labels=None,
        ignore_segments=True,
        create_config=True,
        attrs=None,
    )
    config_file = BratAnnConfiguration()
    segments, relations = brat_converter._get_anns_from_medkit_doc(medkit_doc)
    _ = brat_converter._convert_medkit_anns_to_brat(
        segments, relations, config_file, medkit_doc.text
    )

    assert config_file.entity_types == ["grade", "level", "maladie"]
    assert "normalized" in config_file.attr_entity_values.keys()
    assert "from_umls" in config_file.attr_relation_values.keys()
    assert "related" in config_file.rel_types_arg_1.keys()
    assert "related" in config_file.rel_types_arg_2.keys()

    # already sorted
    assert config_file.to_str() == EXPECTED_CONFIG


def test__convert_segment_to_brat():
    original_text = "segment_text"
    brat_converter = BratOutputConverter()
    segment_medkit = Segment(
        label="label_segment", spans=[Span(0, 12)], text=original_text
    )
    with pytest.raises(AssertionError):
        brat_converter._convert_segment_to_brat(
            segment=segment_medkit, nb_segment=0, raw_text=original_text
        )

    brat_entity = brat_converter._convert_segment_to_brat(
        segment=segment_medkit, nb_segment=1, raw_text=original_text
    )
    assert isinstance(brat_entity, BratEntity)
    assert brat_entity.uid == "T1"
    assert brat_entity.type == "label_segment"
    assert brat_entity.span == ((0, 12),)
    assert brat_entity.text == "segment_text"


def test__convert_attribute_to_brat():
    with pytest.raises(AssertionError):
        BratOutputConverter._convert_attribute_to_brat(
            label="label_attr",
            value=None,
            nb_attribute=0,
            target_brat_id="T1",
            is_from_entity=False,
        )

    brat_attribute, _ = BratOutputConverter._convert_attribute_to_brat(
        label="label_attr",
        value=None,
        nb_attribute=1,
        target_brat_id="T1",
        is_from_entity=False,
    )
    assert isinstance(brat_attribute, BratAttribute)
    assert brat_attribute.uid == "A1"
    assert brat_attribute.type == "label_attr"
    assert brat_attribute.value == ""
    assert brat_attribute.target == "T1"


def test__convert_relation():
    brat_converter = BratOutputConverter()
    ent_1 = Entity(uid="id_1", label="ent_suj", spans=[Span(0, 10)], text="ent_1_text")
    ent_2 = Entity(uid="id_2", label="ent_suj", spans=[Span(0, 10)], text="ent_2_text")
    relation = Relation(label="rel1", source_id=ent_1.uid, target_id=ent_2.uid)

    # create entities brat and save them in a dict
    anns_by_medkit_id = dict()
    anns_by_medkit_id[ent_1.uid] = brat_converter._convert_segment_to_brat(
        ent_1, nb_segment=1, raw_text=ent_1.text
    )
    anns_by_medkit_id[ent_2.uid] = brat_converter._convert_segment_to_brat(
        ent_2, nb_segment=2, raw_text=ent_2.text
    )

    brat_relation, _ = brat_converter._convert_relation_to_brat(
        relation=relation, nb_relation=1, brat_anns_by_segment_id=anns_by_medkit_id
    )
    assert isinstance(brat_relation, BratRelation)
    assert brat_relation.uid == "R1"
    assert brat_relation.subj == anns_by_medkit_id[ent_1.uid].uid
    assert brat_relation.obj == anns_by_medkit_id[ent_2.uid].uid
    assert brat_relation.type == "rel1"
    assert brat_relation.to_str() == "R1\trel1 Arg1:T1 Arg2:T2\n"


def test_doc_names(tmp_path: Path):
    output_path = tmp_path / "output"
    medkit_docs = [_get_medkit_doc(), _get_medkit_doc()]

    brat_converter = BratOutputConverter(
        anns_labels=None,
        ignore_segments=True,
        create_config=True,
        attrs=None,
    )

    with pytest.raises(AssertionError):
        brat_converter.save(medkit_docs, output_path, doc_names=[])

    # names by default
    brat_converter.save(medkit_docs, output_path)

    for medkit_doc in medkit_docs:
        expected_txt_path = output_path / f"{medkit_doc.uid}.txt"
        expected_ann_path = output_path / f"{medkit_doc.uid}.ann"
        assert output_path.exists()
        assert expected_txt_path.exists()
        assert expected_ann_path.exists()
        assert expected_txt_path.read_text() == medkit_doc.text

    # custom names
    expected_names = ["PID_DOC_0", "PID_DOC_1"]
    brat_converter.save(medkit_docs, output_path, doc_names=expected_names)

    for medkit_doc, doc_name in zip(medkit_docs, expected_names):
        expected_txt_path = output_path / f"{doc_name}.txt"
        expected_ann_path = output_path / f"{doc_name}.ann"
        assert output_path.exists()
        assert expected_txt_path.exists()
        assert expected_ann_path.exists()
        assert expected_txt_path.read_text() == medkit_doc.text


def _get_modified_medkit_doc():
    text = "Douleur     abdominale de grade            4"
    doc = TextDocument(uid="doc_brat_2", text=text)
    medkit_anns = [
        Entity(
            spans=[
                Span(0, 7),
                ModifiedSpan(length=1, replaced_spans=[Span(7, 12)]),
                Span(12, 22),
            ],
            label="maladie",
            text="Douleur abdominale",
            uid="e1",
        ),
        Entity(
            spans=[
                Span(26, 31),
                ModifiedSpan(length=1, replaced_spans=[Span(31, 43)]),
                Span(43, 44),
            ],
            label="grade",
            text="grade 4",
            uid="e2",
        ),
    ]
    for ann in medkit_anns:
        doc.anns.add(ann)
    return doc


_EXPECTED_ANN = """T1\tmaladie 0 8;12 22\tDouleur abdominale
T2\tgrade 26 32;43 44\tgrade 4
"""


def test_brat_output_from_modified_span(tmp_path: Path):
    medkit_doc = _get_modified_medkit_doc()
    output_path = tmp_path / "output"
    expected_txt_path = output_path / f"{medkit_doc.uid}.txt"
    expected_ann_path = output_path / f"{medkit_doc.uid}.ann"

    # define a brat output converter
    brat_converter = BratOutputConverter(anns_labels=None, create_config=False)

    brat_converter.save([medkit_doc], output_path)

    assert output_path.exists()
    assert expected_txt_path.exists()
    assert expected_ann_path.exists()
    assert expected_txt_path.read_text() == medkit_doc.text
    assert expected_ann_path.read_text() == _EXPECTED_ANN


def test_normalization_attr(tmp_path: Path):
    """Conversion of normalization objects to strings"""

    text = "Le patient souffre d'asthme"
    doc = TextDocument(text=text)
    entity = Entity(label="maladie", text="asthme", spans=[Span(21, 27)])
    entity.attrs.add(
        EntityNormAttribute(kb_name="umls", kb_id="C0004096", kb_version="2021AB")
    )
    doc.anns.add(entity)

    brat_converter = BratOutputConverter()
    brat_converter.save([doc], tmp_path)

    output_path = tmp_path / f"{doc.uid}.ann"
    ann_lines = output_path.read_text().split("\n")
    assert ann_lines[1] == "A1\tNORMALIZATION T1 umls:C0004096"
