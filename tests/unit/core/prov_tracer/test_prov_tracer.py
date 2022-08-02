from medkit.core.prov_tracer import ProvTracer
from tests.unit.core.prov_tracer._common import Generator, Prefixer, Splitter, Merger


def test_single_item_with_no_source():
    """Very simple use case with only one item generated"""
    tracer = ProvTracer()
    # generate 1 item
    generator = Generator(tracer)
    item = generator.generate(1)[0]

    tracer._graph.check_sanity()

    # tracer must have prov for generated item
    prov = tracer.get_prov(item.id)
    assert prov.data_item == item
    assert prov.op_desc == generator.description
    assert len(prov.source_data_items) == 0
    assert len(prov.derived_data_items) == 0

    assert tracer.get_provs() == [prov]


def test_multiple_items():
    """Very simple use case with several items generated by the same operation"""
    tracer = ProvTracer()
    # generate 2 items
    generator = Generator(tracer)
    items = generator.generate(2)

    tracer._graph.check_sanity()
    # tracer must have prov for each generated item
    assert len(tracer.get_provs()) == len(items)

    for item in items:
        prov = tracer.get_prov(item.id)
        assert prov.data_item == item
        assert prov.op_desc == generator.description


def test_multiple_items_with_sources():
    """Several items generated by an operation, then used as input to another operation
    """
    tracer = ProvTracer()
    # generate 2 items then prefix them
    generator = Generator(tracer)
    prefixer = Prefixer(tracer)
    input_items = generator.generate(2)
    prefixed_items = prefixer.prefix(input_items)

    tracer._graph.check_sanity()
    assert len(tracer.get_provs()) == len(input_items) + len(prefixed_items)

    for input_item, prefixed_item in zip(input_items, prefixed_items):
        input_prov = tracer.get_prov(input_item.id)
        assert input_prov.op_desc == generator.description
        assert len(input_prov.source_data_items) == 0
        # input item was used to derive prefixed item
        assert input_prov.derived_data_items == [prefixed_item]

        prefixed_prov = tracer.get_prov(prefixed_item.id)
        assert prefixed_prov.op_desc == prefixer.description
        # prefixed item was derived from input item
        assert prefixed_prov.source_data_items == [input_item]
        assert len(prefixed_prov.derived_data_items) == 0


def test_intermediate_operation():
    """Input items passed to an intermediate operation, then intermediate items passed to another operatio
    """
    tracer = ProvTracer()
    # generate 2 items and prefix them twice with 2 different operations
    generator = Generator(tracer)
    prefixer_1 = Prefixer(tracer)
    prefixer_2 = Prefixer(tracer)
    input_items = generator.generate(2)
    prefixed_items_1 = prefixer_1.prefix(input_items)
    prefixed_items_2 = prefixer_2.prefix(prefixed_items_1)

    tracer._graph.check_sanity()
    assert len(tracer.get_provs()) == len(input_items) + len(prefixed_items_1) + len(
        prefixed_items_2
    )

    for input_item, prefixed_item_1, prefixed_item_2 in zip(
        input_items, prefixed_items_1, prefixed_items_2
    ):
        input_prov = tracer.get_prov(input_item.id)
        assert input_prov.op_desc == generator.description
        assert len(input_prov.source_data_items) == 0
        # input item was used to derive 1st prefixed item
        assert input_prov.derived_data_items == [prefixed_item_1]

        prefixed_prov_1 = tracer.get_prov(prefixed_item_1.id)
        assert prefixed_prov_1.op_desc == prefixer_1.description
        # 1st prefixed item was derived from input item
        assert prefixed_prov_1.source_data_items == [input_item]
        # 1st prefixed item was used to derive 2st prefixed item
        assert prefixed_prov_1.derived_data_items == [prefixed_item_2]

        prefixed_prov_2 = tracer.get_prov(prefixed_item_2.id)
        assert prefixed_prov_2.op_desc == prefixer_2.description
        # 2d prefixed item was derived from 1st prefixed item
        assert prefixed_prov_2.source_data_items == [prefixed_item_1]
        assert len(prefixed_prov_2.derived_data_items) == 0


def test_multiple_derived():
    """One item used to derive several new items"""
    tracer = ProvTracer()
    # generate 1 item then split it in 2
    generator = Generator(tracer)
    splitter = Splitter(tracer)
    input_items = generator.generate(1)
    input_item = input_items[0]
    split_items = splitter.split(input_items)

    tracer._graph.check_sanity()
    assert len(tracer.get_provs()) == len(input_items) + len(split_items)

    prov = tracer.get_prov(input_item.id)
    assert prov.op_desc == generator.description
    assert len(prov.source_data_items) == 0
    # input item was used to derive 2 split items
    assert prov.derived_data_items == split_items

    for split_item in split_items:
        prov = tracer.get_prov(split_item.id)
        assert prov.op_desc == splitter.description
        # each split item was derived from the input item
        assert prov.source_data_items == [input_item]
        assert len(prov.derived_data_items) == 0


def test_multiple_source():
    """Data items derived from several input items"""
    tracer = ProvTracer()
    # generate 2 item and merge them
    generator = Generator(tracer)
    merger = Merger(tracer)
    input_items = generator.generate(2)
    merged_item = merger.merge(input_items)

    tracer._graph.check_sanity()
    assert (
        len(tracer.get_provs()) == len(input_items) + 1
    )  # 2 input items + 1 merged item

    prov = tracer.get_prov(merged_item.id)
    assert prov.op_desc == merger.description
    # merged item was derived from all input items
    assert prov.source_data_items == input_items

    # all input items were used to derive merged item
    for input_item in input_items:
        prov = tracer.get_prov(input_item.id)
        assert prov.derived_data_items == [merged_item]


def test_partial_provenance():
    """Data items generated from input items for which no provenance info is available
    """
    tracer = ProvTracer()
    # generate 2 items then split them it in 2 them merge them
    # provenance info will be provided only by Merger operation
    generator = Generator(prov_tracer=None)
    splitter = Splitter(prov_tracer=None)
    merger = Merger(tracer)
    input_items = generator.generate(2)
    split_items = splitter.split(input_items)
    merged_item = merger.merge(split_items)

    tracer._graph.check_sanity()
    assert len(tracer.get_provs()) == len(split_items) + 1

    # operation and source data items are available for merged item
    merged_prov = tracer.get_prov(merged_item.id)
    assert merged_prov.op_desc == merger.description
    assert merged_prov.source_data_items == split_items

    # split items have "stub provenance" with no info about how they were generated,
    # but info about how they were used to derive merged item
    split_prov = tracer.get_prov(split_items[0].id)
    assert split_prov.op_desc is None
    assert len(split_prov.source_data_items) == 0
    assert split_prov.derived_data_items == [merged_item]

    # no prov is available for the input items
    assert tracer.has_prov(input_items[0].id) is False
