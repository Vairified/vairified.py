"""members.search() sorting: the API sorts only by PARTNER_SEARCH_SORT_FIELDS
and answers anything else with a 400. Mirrors ``tests/search-sort.test.ts``."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from vairified import (
    PARTNER_SEARCH_SORT_FIELDS,
    SearchFilters,
    Vairified,
    ValidationError,
)

_MESSAGE = (
    "sortField must be one of: lastName, firstName, memberId, city, state, country"
)


class TestSearchSortField:
    def test_exposes_the_six_sortable_fields(self):
        assert PARTNER_SEARCH_SORT_FIELDS == (
            "lastName",
            "firstName",
            "memberId",
            "city",
            "state",
            "country",
        )

    @pytest.mark.parametrize("field", PARTNER_SEARCH_SORT_FIELDS)
    @respx.mock
    async def test_sends_sort_field_unchanged(self, api_key, base_url, field):
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(sort_by=field, sort_order="asc"):
                pass

        params = route.calls.last.request.url.params
        assert params["sortField"] == field
        assert params["sortDirection"] == "asc"

    @respx.mock
    async def test_api_refusal_is_a_validation_error(self, api_key, base_url):
        respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(
                400,
                json={"statusCode": 400, "message": _MESSAGE, "error": "Bad Request"},
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError) as exc:
                # A retired value still reaches the API (no client-side check,
                # as in the TS SDK); its 400 must come back typed.
                async for _ in client.members.search(sort_by="rating"):  # type: ignore[arg-type]
                    pass

        assert exc.value.status_code == 400
        assert exc.value.message == _MESSAGE

    @respx.mock
    async def test_sort_direction_is_sent_only_when_set(self, api_key, base_url):
        # Parity with the TS SDK: unset means "API default" (ascending). This SDK
        # used to send sortDirection=desc on every search.
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(city="Austin"):
                pass
            unset = route.calls.last.request.url.params
            async for _ in client.members.search(city="Austin", sort_order="desc"):
                pass
            desc = route.calls.last.request.url.params

        assert "sortDirection" not in unset
        assert "sortField" not in unset
        assert desc["sortDirection"] == "desc"

    def test_search_filters_sort_field_is_typed_not_runtime_checked(self):
        # The annotation narrows sort_field to the whitelist for type checkers;
        # at runtime the value passes through, as in TypeScript, so the API's
        # 400 is what a bad value produces in both SDKs.
        filters = SearchFilters(sort_field="rating")  # type: ignore[arg-type]
        assert filters.to_query_params() == {"sortField": "rating"}
        assert SearchFilters().to_query_params() == {}
