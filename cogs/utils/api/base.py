import abc
import aiohttp


class APIHTTPExceptionBase(Exception):
    pass

class _APIMeta(type):
    pass

class BaseAPIHTTPClient(object, metaclass=_APIMeta):
    API_BASE_URL = str()
    BASE_EXCEPTION = APIHTTPExceptionBase

    def __init__(self, client):
        self.client = client
        self.session = aiohttp.ClientSession() 

    def __new__(cls, *args, **kwargs):
        if not cls.API_BASE_URL:
            raise ValueError(f"No API_BASE_URL specified in class {cls}")
        return super().__new__(cls)

    @abc.abstractmethod
    def _get_headers(self):
        return dict()

    async def request(self, route, method="POST", data=None, **kwargs):
        url = f"{self.API_BASE_URL}{route}"
        async with self.session.request(method=method, url=url, data=data, headers=self._get_headers(), **kwargs) as resp:
            if resp.status >= 400:
                raise self.BASE_EXCEPTION(f"[{self.__class__.__name__}] API Server responded with status code: {resp.status}.")
            try:
                return await resp.json()
            except aiohttp.ContentTypeError:
                return await resp.read()
