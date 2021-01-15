import asyncio
from io import BytesIO
from aiohttp import ClientSession
from datetime import datetime
from collections import deque
import random as _rand
from typing import Union

from . import utils, types, exceptions


BASE_URL = 'https://www.reddit.com/r/'
ALLOWED_TIMEFRAMES = {
    'now': '?t=hour',
    'hour': '?t=hour',
    'today': '?t=day',
    'week': '?t=week',
    'month': '?t=month',
    'year': '?t=year',
    'all': '?t=all',
}
ALLOWED_METHODS = ('hot', 'new', 'top', 'rising', 'controversial')


class Reddit:
    def __init__(self, url: str, *, cs: ClientSession = None):
        self.last_update = datetime.utcnow()
        self.url = url
        self._cs = cs or ClientSession()
        self.posts = deque()

        is_post, self.sub, self.method = utils.is_post(url)
        if is_post:
            self.target = 'post'
        else:
            self.target = 'subreddit'

    async def _get_response(self, *, override_url: Union[str, None] = None) -> dict:
        url = override_url or self.url
        res = await self._cs.get(url)
        if res.content_type == 'application/json':
            return await res.json()
        elif res.content_type == 'text/html':
            res = await self._cs.get(url + '.json')
            return await res.json()

    async def _get_posts(self, urls: list):
        posts = asyncio.gather(*[self._get_response(override_url=url) for url in urls])
        return posts

    def _load_posts(self):
        if not self.posts:
            self.posts = self._respose.posts

    @classmethod
    def from_sub(cls, sub: str, *, method: str = 'hot', timeframe: str = None, cs: ClientSession = None):
        """Shortcut to allow users to get a picture of the top posts in a given sub with a given filter method
        :param sub: The subreddit to load from
        :type sub: str
        :param method: The sort method of said subreddit
        :type method: str
        :param timeframe: The time filtering to apply to the search
        :type timeframe: str
        :param cs: Option to supply your own ClientSession if one is already running
        :type cs: ClientSession

        :return Reddit:
        """
        if timeframe:
            if timeframe not in ALLOWED_TIMEFRAMES:
                raise exceptions.InvalidTimeFrame(f'Expected one of {" ".join(ALLOWED_TIMEFRAMES.keys())}, got {timeframe} instead.')
            else:
                return cls(f'{BASE_URL}{sub}/{method}/{ALLOWED_TIMEFRAMES[timeframe]}', cs=cs)
        if method not in ALLOWED_METHODS:
            raise exceptions.InvalidSortMethod(f'Expected one of {" ".join(ALLOWED_METHODS)}, got {method} instead')
        return cls(f'{BASE_URL}{sub}/{method}', cs=cs)

    async def load_comments(self):
        """
        This makes a call to the API for comment information in each post the url can see

        :return None:
        """
        if not self.posts:
            self._load_posts()
        urls = [post.full_url for post in self.posts]
        posts = await (await self._get_posts(urls))
        # now `posts` is a list of the json from each post [0] is post, [1] is comments
        for count, post in enumerate(posts):
            comments = post[1]['data']['children']
            for comment in comments:
                if comment['kind'] == 'more':
                    # no way i can see to load the rest of the comments, will fix
                    break
                else:
                    self.posts[count].comments.append(types.Comment(comment['data']))

    def random(self):
        if not self.posts:
            self._load_posts()
        return _rand.choice(self.posts)

    async def change_sub(self, sub: str, *, method: str = 'hot', timeframe: str = None, comments: bool = False):
        if timeframe:
            if timeframe not in ALLOWED_TIMEFRAMES:
                raise exceptions.InvalidTimeFrame(
                    "Expected one of {}, got {} instead".format(' '.join(ALLOWED_TIMEFRAMES.keys()), timeframe))
            else:
                cls = self.__class__("{}{}/{}/{}".format(BASE_URL, sub, method, timeframe), cs=self._cs)
                return await cls.load(comments=comments)
        if method not in ALLOWED_METHODS:
            raise exceptions.InvalidSortMethod(
                "Expected one of {}, got {} instead".format(' '.join(ALLOWED_METHODS), method))
        cls = self.__class__("{}{}/{}".format(BASE_URL, sub, method), cs=self._cs)
        return await cls.load(comments=comments)

    async def fetch_media(self, image: types.Image, *, to_bytes: bool = False) -> Union[BytesIO, bytes]:
        """ # will move this onto the Image objects soon, makes more sense there
        this expects an Image object, as found in post.images
        :param types.Image image: Image object
        :param bool to_bytes: Determines if bytes or BytesIO are returned

        :return Union[BytesIO, bytes]:
        """
        res = await self._cs.get(image.url)

        if res.status == 200:
            out = await res.read()
        elif res.status == 403:
            raise exceptions.ForbiddenUrl("The url tied to this image returns 403 Forbidden; \n{0}".format(image.url))
        else:
            raise NotImplemented

        if to_bytes:
            return out

        out = BytesIO(out)
        out.seek(0)
        return out

    async def load(self, *, comments: bool = False):
        """
        This makes the call to Reddit's API to fetch post & comment information
        :param comments: whether or not to fetch comment data for all posts the original url can see
        :type comments: bool
        :return Reddit:
        """
        # decided to do the api call here instead of in ResponseData's init to avoid asyncio magic
        self._response = types.ResponseData(self.target, self.sub, await self._get_response(), cs=self._cs)
        self._load_posts()
        if comments:
            await self.load_comments()
        return self
