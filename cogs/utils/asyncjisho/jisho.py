import asyncio
from typing import Dict, List, Set, TypeVar, Union

import aiohttp

__all__ = ['Jisho']

# this is to avoid terrible long type hints
# sorry about the not so great readability
T = TypeVar('T')
V = Union[str, List[str]]
LDS = List[Dict[str, T]]  # LDS = List, Dict, String


class Jisho:
    """The class that makes the API requests.
    A class is necessary to safely handle the aiohttp ClientSession
    """
    api_url = 'https://jisho.org/api/v1/search/words'

    def __init__(self, *, loop: asyncio.AbstractEventLoop = None, session: aiohttp.ClientSession = None) -> None:
        if loop is not None and session is not None:
            raise ValueError('Cannot specify both loop and session.')
        elif loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop
        if session is None:
            self._session = aiohttp.ClientSession(loop=self._loop)
            self._close = True
        else:
            self._session = session
            self._close = False

    def __del__(self) -> None:
        # we should always close the session beforehand,
        # but just in case someone doesn't, we'll try
        if self._close:
            try:
                self._loop.create_task(self._session.close())
            except RuntimeError:
                # loop is closed
                pass

    def _parse(self, response: LDS[LDS[V]]) -> LDS[List[str]]:
        results = []

        for data in response:
            readings: Set[str] = set()
            words: Set[str] = set()

            for kanji in data['japanese']:
                reading: str = kanji.get('reading')
                if reading and reading not in readings:
                    readings.add(reading)

                word: str = kanji.get('word')
                if word and word not in words:
                    words.add(word)

            senses: Dict[str, List[str]] = {'english': [], 'parts_of_speech': []}

            for sense in data['senses']:
                senses['english'].extend(sense.get('english_definitions', ()))
                senses['parts_of_speech'].extend(sense.get('parts_of_speech', ()))

            try:
                senses['parts_of_speech'].remove('Wikipedia definition')
            except ValueError:
                pass

            result = {'readings': list(readings), 'words': list(words), **senses}
            results.append(result)

        return results

    async def lookup(self, keyword: str, **kwargs) -> LDS[List[str]]:
        """Search Jisho.org for a word. Returns a list of dicts with keys
        readings, words, english, parts_of_speech.
        """
        params = {'keyword': keyword, **kwargs}
        async with self._session.get(self.api_url, params=params) as resp:
            response = (await resp.json())['data']
        return self._parse(response)

    async def close(self):
        """Closes the internal ClientSession.
        Only use this if you do not plan to reuse the session,
        such as when you do not specify one in the constructor.
        """
        await self._session.close()
        self._close = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._close:
            await self._session.close()
