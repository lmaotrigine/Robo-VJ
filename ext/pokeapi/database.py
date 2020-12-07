import aiosqlite
import re
import collections
from typing import Coroutine, Optional, List, Set, Callable, Tuple, Any, Union
from sqlite3 import Cursor
from .models import *
from contextlib import asynccontextmanager as acm
from discord.utils import get
import random
from launcher import __dirname__

__all__ = 'PokeApi',
__global_cache__ = {}


class PokeApi(aiosqlite.Connection, PokeapiModels):
    @staticmethod
    def _clean_name(name):
        name = name.replace('♀', '_F').replace('♂', '_m').replace('é', 'e')
        name = re.sub(r'\W+', '_', name).title()
        return name

    # generic getters

    @acm
    async def replace_row_factory(self, factory: Callable[[Cursor, Tuple[Any]], Any]):
        old_factory = self.row_factory
        self.row_factory = factory
        yield self
        self.row_factory = old_factory

    def resolve_model(self, model: Union[str, Callable[[Cursor, Tuple[Any]], Any]]) -> Callable[
                      [Cursor, Tuple[Any]], Any]:
        if isinstance(model, str):
            model = getattr(self, model)
        assert issubclass(model, PokeapiResource)
        return model

    async def get_model(self, model: Callable[[Cursor, Tuple[Any]], Any], id_: int) -> Optional[Any]:
        model = self.resolve_model(model)
        if id_ is None:
            return
        if (model, id_) in __global_cache__:
            return __global_cache__[(model, id_)]
        statement = """
        SELECT *
        FROM pokemon_v2_{}
        WHERE id = :id
        """.format(model.__name__.lower())
        async with self.replace_row_factory(model) as conn:
            async with conn.execute(statement, {'id': id_}) as cur:
                result = await cur.fetchone()
        __global_cache__[(model, id_)] = result
        return result

    async def get_all_models(self, model: Callable[[Cursor, Tuple[Any]], Any]) -> List[Any]:
        model = self.resolve_model(model)
        if model in __global_cache__:
            return __global_cache__[model]
        statement = """
        SELECT *
        FROM pokemon_v2_{}
        """.format(model.__name__.lower())
        async with self.replace_row_factory(model) as conn:
            async with conn.execute(statement) as cur:
                result = await cur.fetchall()
        __global_cache__[model] = result
        return result

    async def get(self, model: Callable[[Cursor, Tuple[Any]], Any], **kwargs) -> Optional[Any]:
        return get(await self.get_all_models(model), **kwargs)

    async def filter(self, model: Callable[[Cursor, Tuple[Any]], Any], **kwargs) -> List[Any]:
        iterable = iter(await self.get_all_models(model))
        results = []
        while (record := get(iterable, **kwargs)) is not None:
            results.append(record)
        return results

    async def get_model_named(self, model: Callable[[Cursor, Tuple[Any]], Any], name: str) -> Optional[Any]:
        obj = await self.get(model, name=name)
        if obj:
            __global_cache__[(model, obj.id)] = obj
        return obj

    async def get_names_from(self, table: Callable[[Cursor, Tuple[Any]], Any], *, clean=False) -> List[str]:
        """Generic method to get a list of all names from a PokeApi table."""
        names = [await self.get_name(obj, clean=clean) for obj in await self.get_all_models(table)]
        return names

    async def get_name(self, item: NamedPokeapiResource, *, clean=False) -> str:
        return self._clean_name(item.name) if clean else item.name

    async def get_name_by_id(self, model: Callable[[Cursor, Tuple[Any]], Any], id_: int, *, clean=False):
        """Generic method to get the name of a PokeApi object given only its ID."""
        obj = await self.get_model(model, id_)
        return obj and await self.get_name(obj, clean=clean)

    async def get_random(self, model: Callable[[Cursor, Tuple[Any]], Any]) -> Optional[Any]:
        """Generic method to get a random PokeApi object."""
        model = self.resolve_model(model)
        if model in __global_cache__:
            return random.choice(__global_cache__[model])
        statement = """
        SELECT *
        FROM pokemon_v2_{}
        ORDER BY random()
        """.format(model.__name__.lower())
        async with self.replace_row_factory(model) as conn:
            async with conn.execute(statement) as cur:
                obj = await cur.fetchone()
        __global_cache__[(model, obj.id)] = obj
        return obj

    async def get_random_name(self, table: Callable[[Cursor, Tuple[Any]], Any], *, clean=False) -> Optional[str]:
        """Generic method to get a random PokeApi object name."""
        obj = await self.get_random(table)
        return obj and await self.get_name(obj, clean=clean)

    # Specific getters, defined for typehints

    def get_species(self, id_) -> Coroutine[None, None, Optional[PokeapiModels.PokemonSpecies]]:
        """Get a Pokemon species by ID"""
        return self.get_model(PokeapiModels.PokemonSpecies, id_)

    def random_species(self) -> Coroutine[None, None, Optional[PokeapiModels.PokemonSpecies]]:
        """Get a random Pokemon species"""
        return self.get_random(PokeapiModels.PokemonSpecies)

    def get_mon_name(self, mon: PokeapiModels.PokemonSpecies, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of a Pokemon species"""
        return self.get_name(mon, clean=clean)

    def random_species_name(self, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of a random Pokemon species"""
        return self.get_random_name(PokeapiModels.PokemonSpecies, clean=clean)

    def get_species_by_name(self, name: str) -> Coroutine[None, None, Optional[PokeapiModels.PokemonSpecies]]:
        """Get a Pokemon species given its name"""
        return self.get_model_named(PokeapiModels.PokemonSpecies, name)

    def get_forme_name(self, mon: PokeapiModels.PokemonForm, *, clean=False) -> Coroutine[None, None, str]:
        """Get a Pokemon forme's name"""
        return self.get_name(mon, clean=clean)

    def random_move(self) -> Coroutine[None, None, Optional[PokeapiModels.Move]]:
        """Get a random move"""
        return self.get_random(PokeapiModels.Move)

    def get_move_name(self, move: PokeapiModels.Move, *, clean=False) -> Coroutine[None, None, str]:
        """Get a move's name"""
        return self.get_name(move, clean=clean)

    def random_move_name(self, *, clean=False) -> Coroutine[None, None, str]:
        """Get a random move's name"""
        return self.get_random_name(PokeapiModels.Move, clean=clean)

    def get_move_by_name(self, name: str) -> Coroutine[None, None, Optional[PokeapiModels.Move]]:
        """Get a move given its name"""
        return self.get_model_named(PokeapiModels.Move, name)

    def get_mon_color(self, mon: PokeapiModels.PokemonSpecies) -> PokeapiModels.PokemonColor:
        """Get the object representing the Pokemon species' color"""
        return mon.pokemon_color

    def get_pokemon_color_by_name(self, name: str) -> Coroutine[None, None, Optional[PokeapiModels.PokemonColor]]:
        """Get a Pokemon color given its name"""
        return self.get_model_named(PokeapiModels.PokemonColor, name)

    def get_pokemon_color_name(self, color: PokeapiModels.PokemonColor, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of a Pokemon color"""
        return self.get_name(color, clean=clean)

    def get_name_of_mon_color(self, mon: PokeapiModels.PokemonSpecies, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of a Pokemon species' color"""
        return self.get_name(mon.pokemon_color, clean=clean)

    def get_ability_by_name(self, name: str) -> Coroutine[None, None, Optional[PokeapiModels.Ability]]:
        """Get an ability given its name"""
        return self.get_model_named(PokeapiModels.Ability, name)

    def get_ability_name(self, ability: PokeapiModels.Ability, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of an ability"""
        return self.get_name(ability, clean=clean)

    def get_type_by_name(self, name: str) -> Coroutine[None, None, Optional[PokeapiModels.Type]]:
        """Get a Pokemon type given its name"""
        return self.get_model_named(PokeapiModels.Type, name)

    def get_type_name(self, type_: PokeapiModels.Type, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of a type"""
        return self.get_name(type_, clean=clean)

    def get_pokedex_by_name(self, name: str) -> Coroutine[None, None, Optional[PokeapiModels.Pokedex]]:
        """Get a Pokedex given its name"""
        return self.get_model_named(PokeapiModels.Pokedex, name)

    def get_pokedex_name(self, dex: PokeapiModels.Pokedex, *, clean=False) -> Coroutine[None, None, str]:
        """Get the name of a pokedex"""
        return self.get_name(dex, clean=clean)

    # Aliases

    get_pokemon = get_species
    random_pokemon = random_species
    get_pokemon_name = get_mon_name
    get_species_name = get_mon_name
    get_pokemon_species_name = get_mon_name
    random_pokemon_name = random_species_name
    get_pokemon_by_name = get_species_by_name
    get_pokemon_species_by_name = get_species_by_name
    get_color_by_name = get_pokemon_color_by_name
    get_color_name = get_pokemon_color_name

    # Nonstandard methods

    async def get_mon_types(self, mon: PokeapiModels.PokemonSpecies) -> List[PokeapiModels.Type]:
        """Returns a list of types for that Pokemon"""
        result = [montype.type for montype in
                  await self.filter(PokeapiModels.PokemonType, pokemon__pokemon_species=mon, pokemon__is_default=True)]
        return result

    async def get_mon_matchup_against_type(self, mon: PokeapiModels.PokemonSpecies, type_: PokeapiModels.Type) -> float:
        """Calculates whether a type is effective or not against a mon"""
        result = 1
        for target_type in await self.filter(PokeapiModels.PokemonType, pokemon__pokemon_species=mon,
                                             pokemon__is_default=True):
            efficacy = await self.get(PokeapiModels.TypeEfficacy, damage_type=type_, target_type=target_type.type)
            result *= efficacy.damage_factor / 100
        return result

    async def get_mon_matchup_against_move(self, mon: PokeapiModels.PokemonSpecies, move: PokeapiModels.Move) -> float:
        """Calculates whether a move is effective or not against a mon"""
        return await self.get_mon_matchup_against_type(mon, move.type)

    async def get_mon_matchup_against_mon(self, mon: PokeapiModels.PokemonSpecies,
                                          mon2: PokeapiModels.PokemonSpecies) -> List[float]:
        """For each type mon2 has, determines its effectiveness against mon"""
        res = collections.defaultdict(lambda: 1)
        damage_types = await self.filter(PokeapiModels.PokemonType, pokemon__pokemon_species=mon2,
                                         pokemon__is_default=True)
        target_types = await self.filter(PokeapiModels.PokemonType, pokemon__pokemon_species=mon,
                                         pokemon__is_default=True)
        print(damage_types)
        print(target_types)
        for damage_type in damage_types:
            for target_type in target_types:
                efficacy = await self.get(PokeapiModels.TypeEfficacy, damage_type=damage_type.type,
                                          target_type=target_type.type)
                res[damage_type.type] *= efficacy.damage_factor / 100
        return list(res.values())

    async def get_preevo(self, mon: PokeapiModels.PokemonSpecies) -> PokeapiModels.PokemonSpecies:
        """Get the species the given Pokemon evoles from"""
        return mon.evolves_from_species

    async def get_evos(self, mon: PokeapiModels.PokemonSpecies) -> List[PokeapiModels.PokemonSpecies]:
        """Get all species the given Pokemon evolves into"""
        result = [mon2 for mon2 in await self.filter(PokeapiModels.PokemonSpecies, evolves_from_species=mon)]
        return result

    async def get_mon_learnset(self, mon: PokeapiModels.PokemonSpecies) -> Set[PokeapiModels.Move]:
        """Returns a list of all the moves the Pokemon can learn"""
        result = set(learn.move for learn in await self.filter(PokeapiModels.PokemonMove, pokemon__pokemon_species=mon,
                                                               pokemon__is_default=True))
        return result

    async def mon_can_learn_move(self, mon: PokeapiModels.PokemonSpecies, move: PokeapiModels.Move) -> bool:
        """Returns whether a move is in the Pokemon's learnset"""
        result = await self.get(PokeapiModels.PokemonMove, move=move, pokemon__pokemon_species=mon,
                                pokemon__is_default=True)
        return result is not None

    async def get_mon_abilities(self, mon: PokeapiModels.PokemonSpecies) -> List[PokeapiModels.Ability]:
        """Returns a list of abilities for that Pokemon"""
        result = [ability.ability for ability in
                  await self.filter(PokeapiModels.PokemonAbility, pokemon__pokemon_species=mon,
                                    pokemon__is_default=True)]
        return result

    async def mon_has_ability(self, mon: PokeapiModels.PokemonSpecies, ability: PokeapiModels.Ability) -> bool:
        """Returns whether a Pokemon can have a given ability"""
        result = await self.get(PokeapiModels.PokemonAbility, ability=ability, pokemon__pokemon_species=mon,
                                pokemon__is_default=True)
        return result is not None

    async def mon_has_type(self, mon: PokeapiModels.PokemonSpecies, type_: PokeapiModels.Type) -> bool:
        """Returns whether the Pokemon has the given type. Only accounts for base forms."""
        result = await self.get(PokeapiModels.PokemonType, pokemon__pokemon_species=mon, pokemon__is_default=True,
                                type=type_)
        return result is not None

    async def has_mega_evolution(self, mon: PokeapiModels.PokemonSpecies) -> bool:
        """Returns whether the Pokemon can Mega Evolve"""
        result = await self.get(PokeapiModels.PokemonForm, is_mega=True, pokemon__pokemon_species=mon)
        return result is not None

    async def get_evo_line(self, mon: PokeapiModels.PokemonSpecies) -> List[PokeapiModels.PokemonSpecies]:
        """Returns the set of all Pokemon in the same evolution family as the given species."""
        result = [mon2 for mon2 in await self.filter(PokeapiModels.PokemonSpecies, evolution_chain=mon.evolution_chain)]
        return result

    async def mon_is_in_dex(self, mon: PokeapiModels.PokemonSpecies, dex: PokeapiModels.Pokedex) -> bool:
        """Returns whether a Pokemon is in the given pokedex."""
        result = await self.get(PokeapiModels.PokemonDexNumber, pokemon_species=mon, pokedex=dex)
        return result is not None

    async def get_formes(self, mon: PokeapiModels.PokemonSpecies) -> List[PokeapiModels.PokemonForm]:
        result = [form for form in await self.filter(PokeapiModels.PokemonForm, pokemon__pokemon_species=mon)]
        return result

    async def get_default_forme(self, mon: PokeapiModels.PokemonSpecies) -> PokeapiModels.PokemonForm:
        result = await self.get(PokeapiModels.PokemonForm, pokemon__pokemon_species=mon, is_default=True)
        return result

    async def get_sprite_path(self, mon: PokeapiModels.Pokemon, name: str) -> Optional[str]:
        sprites: PokeapiModels.PokemonSprites = await self.get(PokeapiModels.PokemonSprites, pokemon=mon)
        path = sprites.sprites
        for entry in name.split('/'):
            try:
                path = path[entry]
            except (KeyError, TypeError):
                return None
        if isinstance(path, (dict, list)):
            path = None
        return path

    async def get_sprite_local_path(self, mon: PokeapiModels.Pokemon, name: str) -> Optional[str]:
        path = await self.get_sprite_path(mon, name)
        if path:
            path = re.sub(r'^/media/', f'{__dirname__}/pokeapi/data/v2/sprites/', path)
        return path

    async def get_sprite_url(self, mon: PokeapiModels.Pokemon, name: str) -> Optional[str]:
        path = await self.get_sprite_path(mon, name)
        if path:
            path = re.sub(r'^/media/', 'https://raw.githubusercontent.com/PokeAPI/sprites/master/', path)
        return path

    async def get_species_sprite_url(self, mon: PokeapiModels.PokemonSpecies) -> Optional[str]:
        forme = await self.get_default_forme(mon)
        poke = forme.pokemon
        attempts = [
            'versions/generation-vii/ultra-sun-ultra-moon/front_default',
            'versions/generation-vi/icons/front_default'
        ]
        for name in attempts:
            if path := await self.get_sprite_url(poke, name):
                return path
