from . import BaseAPIHTTPClient
import datetime
import config

def _get_datetime(string):
    try:
        return datetime.datetime.strptime(string, "%Y-%m-%d")
    except (ValueError, TypeError):
        return

class TMDBAPIException(Exception):
    pass

class Cast(object):
    def __init__(self, *, character, name, order, **_kwargs):
        self.name = name
        self.order = order
        self.character = character

class Crew(object):
    def __init__(self, *, department, job, name, **_kwargs):
        self.name = name
        self.job = job
        self.department = department

class Credits(object):
    def __init__(self, *, cast, crew, **_kwargs):
        self.cast = sorted([Cast(**_) for _ in cast], key=lambda c: c.order)
        self.crew = [Crew(**_) for _ in crew]
        self.director = self.__get_crew_with_job("DIRECTOR")
        self.writer = self.__get_crew_with_job("WRITER")
        self.screenplay = self.__get_crew_with_job("SCREENPLAY")

    def __get_crew_with_job(self, job):
        try:
            return [crew for crew in self.crew if crew.job.upper() == job.upper()][0]
        except IndexError:
            return

class PartialMovie(object):
    DEFAULT_SIZE = "original"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/{size}{file_path}"

    def _get_image_url(self, path, size=DEFAULT_SIZE):
        return self.IMAGE_BASE_URL.format(size=size, file_path=path)

    def __init__(self, *, poster_path, adult, overview, original_title, ratings, **kwargs):
        self.id = kwargs.pop("id")
        self.title = original_title
        self.nsfw = adult
        self.overview = overview
        self.poster = self._get_image_url(poster_path)
        self.credits = kwargs.get("credits")
        self.ratings = ratings

class Movie(PartialMovie):
    def __init__(self, *, genres, homepage, budget, imdb_id, release_date, revenue, vote_count, production_companies, status, spoken_languages, production_countries, **kwargs):
        super().__init__(**kwargs)
        self.homepage = homepage
        self.genres = [g["name"] for g in genres]
        self.budget = budget
        self.imdb_id = imdb_id
        self.revenue = revenue
        self.votes = vote_count
        self.status = status
        self.release_date = _get_datetime(release_date)
        self.productions = [p["name"] for p in production_companies]
        self.languages = [lang["name"] for lang in spoken_languages]
        self.countries = [c["name"] for c in production_countries]

class PartialTVShow(PartialMovie):
    def __init__(self, *, first_air_date, **kwargs):
        super().__init__(adult=None, original_title=kwargs['name'], **kwargs)
        self.first_air_date = _get_datetime(first_air_date)

class TVShowEpisode(object):
    def __init__(self, *, air_date, episode_number, name, overview, season_number, ratings, **_kwargs):
        self.air_date = _get_datetime(air_date)
        self.episode_number = episode_number
        self.name = name
        self.overview = overview
        self.season_number = season_number
        self.ratings = ratings

class TVShowSeason(TVShowEpisode):
    def __init__(self, *, episode_count, **kwargs):
        super().__init__(**kwargs)
        self.episode_count = episode_count

class TVShow(Movie, PartialTVShow):
    def __init__(self, *, created_by, in_production, last_air_date, last_episode_to_air, next_episode_to_air, number_of_episodes, number_of_seasons, seasons, status, **kwargs):
        Movie.__init__(self, budget=None, imdb_id=kwargs.get('imdb_id'), release_date=None, revenue=None, status=status, spoken_languages=tuple(), production_countries=tuple(), **kwargs)
        PartialTVShow.__init__(self, **kwargs)
        self.creators = [c["name"] for c in created_by]
        self.in_production = in_production
        self.last_air_date = _get_datetime(last_air_date)
        self.last_episode = TVShowEpisode(**last_episode_to_air)
        self.next_episode = TVShowEpisode(**next_episode_to_air) if next_episode_to_air else None
        self.episodes_count = number_of_episodes
        self.seasons_count = number_of_seasons
        self.seasons = seasons
        self.status = status
        self.type = kwargs.get("type")

class TMDBHTTPClient(BaseAPIHTTPClient):
    API_BASE_URL = "https://api.themoviedb.org/3"
    BASE_EXCEPTION = TMDBAPIException

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.client.access_token}"
        }

    async def fetch_movie_data(self, id_, extras=("credits",)):
        params = dict(append_to_response=",".join(extras))
        return await self.request(f"/movie/{id_}", method="GET", params=params)
    
    async def fetch_tvshow_data(self, id_, extras=("credits",)):
        params = dict(append_to_response=",".join(extras))
        return await self.request(f"/tv/{id_}", method="GET", params=params)

    async def search_movie(self, query):
        params = dict(query=query, include_adult="true")
        data = await self.request("/search/movie", method="GET", params=params)
        return data.get("results") or []

    async def search_tvshow(self, query):
        params = dict(query=query, include_adult="true")
        data = await self.request("/search/tv", method="GET", params=params)
        return data.get("results") or []

    async def search_any(self, query):
        params = dict(query=query, include_adult="true")
        data = await self.request("/search/multi", method="GET", params=params)
        return data.get("results") or []

    async def fetch_movie_credits(self, movie_id):
        return await self.request(f"/movie/{movie_id}/credits", method="GET")

    async def fetch_tvshow_credits(self, tvshow_id):
        return await self.request(f"/tv/{tvshow_id}/credits", method="GET")

    async def fetch_tv_imdb_id(self, tvshow_id):
        data = await self.request(f"/tv/{tvshow_id}/external_ids", method="GET")
        return data.get("imdb_id")

    async def fetch_movie_imdb_id(self, movie_id):
        data = await self.request(f"/movie/{movie_id}/external_ids", method="GET")
        return data.get("imdb_id")
    

class Ratings:
    def __init__(self, *, imdb=None, imdb_votes=None, metascore=None, rtomatoes=None):
        self.imdb = imdb
        self.imdb_votes = imdb_votes
        self.metascore = metascore
        self.rtomatoes = rtomatoes

    @classmethod
    def from_data(cls, data):
        ratings = data.get("Ratings")
        self = cls.__new__(cls)
        if not ratings:
            return self
        for rating in ratings:
            if rating['Source'] == "Internet Movie Database":
                self.imdb = rating['Value']
            elif rating['Source'] == "Rotten Tomatoes":
                self.rtomatoes = rating['Value']
            elif rating['Source'] == "Metacritic":
                self.metascore = rating["Value"]
        self.imdb_votes = data.get("imdbVotes")
        return self 

class TMDBClient(object):
    def __init__(self, access_token=config.tmdb_access_token):
        self.access_token = access_token
        self.http = TMDBHTTPClient(self)

    async def fetch_ratings(self, imdb_id):
        if imdb_id is None:
            return Ratings()
        async with self.http.session.get("http://www.omdbapi.com", params={"apikey": config.omdb_api_key, "i": imdb_id}) as resp:
            if resp.status != 200:
                return Ratings()
            data = await resp.json()
            if not data['Response']:
                return Ratings()
            return Ratings.from_data(data)

    async def fetch_movie(self, movie_id) -> Movie:
        data = await self.http.fetch_movie_data(movie_id)
        imdb_id = await self.http.fetch_movie_imdb_id(movie_id)
        ratings = await self.fetch_ratings(imdb_id)
        return Movie(ratings=ratings, **data, credits=Credits(**data.pop("credits")))

    async def search_movie(self, query) -> list:
        results = await self.http.search_movie(query)
        return [PartialMovie(**_) for _ in results]

    async def fetch_movie_from_search(self, query) -> Movie:
        results = await self.search_movie(query)
        try:
            return await self.fetch_movie(results[0].id)
        except IndexError:
            pass

    async def fetch_tvshow(self, tvshow_id) -> TVShow:
        data = await self.http.fetch_tvshow_data(tvshow_id)
        imdb_id = await self.http.fetch_tv_imdb_id(tvshow_id)
        ratings = await self.fetch_ratings(imdb_id)
        return TVShow(ratings=ratings, **data, credits=Credits(**data.pop("credits")))

    async def search_tvshow(self, query) -> list:
        results = await self.http.search_tvshow(query)
        return [PartialTVShow(**_) for _ in results]

    async def fetch_tvshow_from_search(self, query) -> TVShow:
        results = await self.search_tvshow(query)
        try:
            return await self.fetch_tvshow(results[0].id)
        except IndexError:
            pass
