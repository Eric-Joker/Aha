# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from time import time
from typing import Optional

import aiohttp
from pydantic import Field
from sqlalchemy import insert, select
from tenacity import retry, stop_after_attempt, wait_exponential
from yarl import URL

from cores import RobustBaseModel
from services.database import db_session_factory

from .database import GithubSearch


class LicenseInfo(RobustBaseModel):
    key: Optional[str]
    name: Optional[str]
    spdx_id: Optional[str]
    url: Optional[str]


class Repository(RobustBaseModel):
    name: Optional[str]
    description: Optional[str]
    language: Optional[str]
    forks: Optional[int] = Field(alias="forks_count")
    stars: Optional[int] = Field(alias="stargazers_count")
    watchers: Optional[int] = Field(alias="subscribers_count")
    license: Optional[LicenseInfo] = None
    created_at: Optional[str]
    updated_at: Optional[str]
    html_url: Optional[str]


class User(RobustBaseModel):
    login: Optional[str]
    type: Optional[str]
    following: Optional[int]
    followers: Optional[int]
    public_repos: Optional[int]
    public_gists: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]
    html_url: Optional[str]


class GithubClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._base_url = URL("https://api.github.com")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    async def _fetch_api(self, endpoint: str, params: dict = None) -> dict:
        async with self._session.get(self._base_url / endpoint, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_repo(self, repo: str):
        try:
            return Repository(**await self._fetch_api(f"repos/{repo}"))
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise

    async def get_user(self, username: str):
        try:
            return User(**await self._fetch_api(f"users/{username}"))
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise

    async def search_repos(self, query: str, limit: int = 5):
        return (
            item["full_name"]
            for item in (await self._fetch_api("search/repositories", {"q": query, "per_page": limit, "sort": "stars"})).get(
                "items", []
            )
        )

    async def cache_search(self, user_id: int, query: str, limit: int = 5):
        """缓存搜索结果"""
        current_time = int(time())
        if results := tuple(await self.search_repos(query, limit)):
            async with db_session_factory() as session:
                await session.execute(
                    insert(GithubSearch)
                    .values(user_id=user_id, results=results, timestamp=current_time)
                    .prefix_with("OR REPLACE")
                )
                await session.commit()
        return results

    async def get_cached_repo(self, user_id: int, index: int):
        """获取缓存结果"""
        current_time = int(time())
        async with db_session_factory() as session:
            record = await session.scalar(
                select(GithubSearch)
                .where(GithubSearch.user_id == user_id, GithubSearch.timestamp >= current_time - 300)
                .order_by(GithubSearch.timestamp.desc())
                .limit(1)
            )

            if not record or index >= len(record.results):
                return None

            return await self.get_repo(record.results[index])
