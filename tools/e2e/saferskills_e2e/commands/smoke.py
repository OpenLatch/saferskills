"""HTTP contract smoke tests.

Two assertions, each with its own dedicated exit code so CI can tell
"the API is up but /openapi.json regressed" apart from "the API isn't
even healthy":

  * `GET /api/v1/health` -> 200 + `{"status": "ok"}` -> ExitCode.FAIL_HEALTH
  * `GET /openapi.json`  -> parses + `info.title == "SaferSkills API"` -> ExitCode.FAIL_OPENAPI
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.fixtures import (
    FixtureError,
    assert_json_has_keys,
    assert_json_value,
)
from saferskills_e2e.shared.http_client import make_client
from saferskills_e2e.shared.output import print_fail, print_ok

EXPECTED_OPENAPI_TITLE = "SaferSkills API"


class SmokeCommand(BaseCommand):
    name = "smoke"
    description = "Health + OpenAPI HTTP-contract assertions"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()

        async with make_client(config) as client:
            health_code = await self._check_health(client, config)
            if health_code is not ExitCode.OK:
                # Stop at the first failure — running openapi assertions
                # against a sick API just adds noise to the log. Each
                # failure path keeps its own specific exit code.
                return health_code

            openapi_code = await self._check_openapi(client, config)
            if openapi_code is not ExitCode.OK:
                return openapi_code

        return ExitCode.OK

    async def _check_health(
        self, client: httpx.AsyncClient, config: Config
    ) -> ExitCode:
        url = f"{config.api_url}/api/v1/health"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            print_fail(f"GET {url} transport error: {e!s}")
            return ExitCode.FAIL_HEALTH

        if resp.status_code != 200:
            print_fail(f"GET {url} expected 200, got {resp.status_code}")
            return ExitCode.FAIL_HEALTH

        try:
            body: object = resp.json()
            assert_json_value(assert_json_has_keys(body, ("status",)), "status", "ok")
        except (FixtureError, json.JSONDecodeError) as e:
            print_fail(f"GET {url} body assertion failed: {e!s}")
            return ExitCode.FAIL_HEALTH

        print_ok("GET /api/v1/health returns 200 + status=ok")
        return ExitCode.OK

    async def _check_openapi(
        self, client: httpx.AsyncClient, config: Config
    ) -> ExitCode:
        url = f"{config.api_url}/openapi.json"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as e:
            print_fail(f"GET {url} transport error: {e!s}")
            return ExitCode.FAIL_OPENAPI

        if resp.status_code != 200:
            print_fail(f"GET {url} expected 200, got {resp.status_code}")
            return ExitCode.FAIL_OPENAPI

        try:
            body: object = resp.json()
        except json.JSONDecodeError as e:
            print_fail(f"GET {url} response is not valid JSON: {e!s}")
            return ExitCode.FAIL_OPENAPI

        try:
            spec = assert_json_has_keys(body, ("info",))
            info_obj: Any = spec["info"]
            info = assert_json_has_keys(info_obj, ("title",))
            assert_json_value(info, "title", EXPECTED_OPENAPI_TITLE)
        except FixtureError as e:
            print_fail(f"GET {url} OpenAPI shape regression: {e!s}")
            return ExitCode.FAIL_OPENAPI

        print_ok(
            f"GET /openapi.json parses and carries info.title={EXPECTED_OPENAPI_TITLE!r}"
        )
        return ExitCode.OK
