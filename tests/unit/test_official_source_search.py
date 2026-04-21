from agent_integrations.official_source_search import apply_source_policy, shape_query


def test_shape_query_strips_wrapper_and_preserves_official_keyword() -> None:
    query = shape_query(
        'Search the web for: Python dataclasses official docs what is the exact page title?',
        prefer_official=True,
    )

    assert query == 'Python dataclasses official docs'


def test_apply_source_policy_prioritizes_preferred_domains() -> None:
    results = [
        {'title': 'Community post', 'link': 'https://example.com/post'},
        {'title': 'Official docs', 'link': 'https://docs.python.org/3/library/dataclasses.html'},
    ]

    ranked = apply_source_policy(
        results,
        source_policy='preferred_first',
        preferred_domains=['docs.python.org'],
    )

    assert [item['title'] for item in ranked] == ['Official docs', 'Community post']

