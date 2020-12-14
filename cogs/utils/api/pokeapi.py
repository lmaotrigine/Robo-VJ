import random
import aiohttp


class PokeAPIException(Exception):
    pass


class PokeAPI:
    def __init__(self, bot):
        self.bot = bot
        self.session = self.bot.session

    BASE_URL = 'https://pokeapi.co/api/v2/'
    BASE_EXCEPTION = PokeAPIException

    async def request(self, route, method="GET", data=None, **kwargs):
            url = f"{self.BASE_URL}{route}"
            async with self.session.request(method=method, url=url, data=data, **kwargs) as resp:
                if resp.status >= 400:
                    raise self.BASE_EXCEPTION(
                        f"[{self.__class__.__name__}] API Server responded with status code: {resp.status}.")
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return await resp.read()

    async def get_random_pokemon(self):
        data = await self.request('pokemon')
        limit = data.get('count')
        all_poke = await self.request('pokemon', params={'limit': limit})
        return random.choice(all_poke['results'])

    async def get_species_sprite_url(self, poke):
        async with self.session.get(poke['url']) as resp:
            data = await resp.json()
        sprites = data['sprites']

        if sprites.get('front_default'):
            return sprites['front_default']
        try:
            return sprites['versions']['generation-vii']['ultra-sun-ultra-moon']['front_default']
        except KeyError:
            try:
                return sprites['versions']['generation-viii']['icons']['front_default']
            except KeyError:
                return None
