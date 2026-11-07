from apps.core.chain import first_break, sign

KEY = b"key"


def chain(*contents: str) -> list[tuple[dict[str, str], str]]:
    records: list[tuple[dict[str, str], str]] = []
    previous = ""
    for content in contents:
        fields = {"content": content}
        previous = sign(KEY, fields, previous)
        records.append((fields, previous))
    return records


def test_an_untouched_chain_checks_out() -> None:
    assert first_break(KEY, chain("one", "two", "three")) is None
    assert first_break(KEY, []) is None


def test_an_edit_is_caught_where_it_happened() -> None:
    records = chain("one", "two", "three")
    records[1] = ({"content": "changed"}, records[1][1])
    assert first_break(KEY, records) == 1


def test_a_removed_record_is_caught() -> None:
    records = chain("one", "two", "three")
    del records[1]
    assert first_break(KEY, records) == 1


def test_an_inserted_record_is_caught_even_with_a_real_signature() -> None:
    records = chain("one", "two")
    records.insert(1, chain("forged")[0])
    assert first_break(KEY, records) == 1


def test_someone_without_the_key_cannot_forge_a_chain() -> None:
    assert first_break(b"other key", chain("one")) == 0


def test_the_same_words_get_a_different_signature_later_in_a_chain() -> None:
    records = chain("hello", "hello")
    assert records[0][1] != records[1][1]


def test_a_signature_with_odd_characters_is_a_break_not_a_crash() -> None:
    records = chain("one", "two")
    records[1] = (records[1][0], "\u0645\u0639")
    assert first_break(KEY, records) == 1


def test_cutting_the_newest_records_off_is_not_noticed() -> None:
    assert first_break(KEY, chain("one", "two", "three")[:2]) is None
