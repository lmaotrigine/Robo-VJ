import datetime
import discord
from discord.ext import commands

import dateutil.parser
import inspect
import re


def duration_to_string(duration: datetime.timedelta, weeks: bool = True,
                       milliseconds: bool = False, microseconds: bool = False,
                       abbreviate: bool = False, separator: str = ' ') -> str:
    # TODO: Support colon format
    # TODO: Default output for duration of 0?
    if not isinstance(duration, datetime.timedelta):
        raise RuntimeError("duration must be datetime.timedelta")
    negative = False
    if duration.total_seconds() < 0:
        duration = abs(duration)
        negative = True
    units = {"year": duration.days // 365}
    if weeks:
        units["week"] = duration.days % 365 // 7
        units["day"] = duration.days % 365 % 7
    else:
        units["day"] = duration.days % 365
    units["hour"] = duration.seconds // 3600
    units["minute"] = duration.seconds // 60 % 60
    units["second"] = duration.seconds % 60
    if milliseconds:
        units["millisecond"] = duration.microseconds // 1000
        if microseconds:
            units["microsecond"] = duration.microseconds % 1000
    elif microseconds:
        units["microsecond"] = duration.microseconds
    outputs = []
    for name, value in units.items():
        if not value:
            continue
        if negative:
            value = -value
        if abbreviate:
            if name == "millisecond":
                output = f"{value}ms"
            elif name == "microsecond":
                output = f"{value}μs"
            else:
                output = f"{value}{name[0]}"
        else:
            output = f"{value} {name}"
            if abs(value) > 1:
                output += 's'
        outputs.append(output)
    return separator.join(outputs)


class Astronomy(commands.Cog):
    """Space"""

    def __init__(self, bot):
        self.bot = bot
        # Add specific astronomy subcommands as commands
        for name, command in inspect.getmembers(self):
            if isinstance(command, commands.Command) and name in ('exoplanet', 'iss', 'observatory', 'telescope'):
                self.bot.add_command(command)

    # TODO: random exoplanet, observatory, telescope

    @commands.group(aliases=['space'], invoke_without_command=True)
    async def astronomy(self, ctx):
        """exoplanet, iss, observatory, and telescope are commands as well as subcommands."""
        await ctx.send_help(ctx.command)

    @astronomy.command()
    async def chart(self, ctx, *, chart: str):
        """WIP"""
        # paginate, https://api.arcsecond.io/findingcharts/HD%205980/
        ...

    @astronomy.group(aliases=['archive', 'archives'], invoke_without_command=True)
    async def data(self, ctx):
        """Data archives"""
        await ctx.send_help(ctx.command)

    @data.command(name='eso')
    async def data_eso(self, ctx, programme_id: str):
        """European Southern Observatory
        http://archive.eso.org/wdb/wdb/eso/sched_rep_arc/query
        http://archive.eso.org/wdb/help/eso/schedule.html
        http://archive.eso.org/eso/eso_archive_main.html
        http://telbib.eso.org/
        """
        url = f'https://api.arcsecond.io/archives/ESO/{programme_id}/summary/'
        params = {'format': 'json'}
        async with ctx.session.get(url, params=params) as resp:
            if resp.status == 404:
                return await ctx.reply(':no_entry: Error: Not found.')
            data = await resp.json()
        # TODO: Handle errors
        # TODO: include programme_type?, remarks?, abstract?, observer_name?
        links = []
        if data['abstract_url']:
            links.append('[Abstract]({})'.format(data['abstract_url'].replace(')', '\\)')))
        if data['raw_files_url']:
            links.append('[Raw Files]({})'.format(data['raw_files_url'].replace(')', '\\)')))
        if data['publications_url']:
            links.append(f'[Publications]({data["publications_url"]})')
        embed = discord.Embed(description='\n'.join(links))
        if data['programme_title'] != '(Undefined)':
            embed.title = data['programme_title']

        if data['period']:
            embed.add_field(name='Period', value=data['period'])
        if data['observing_mode'] != '(Undefined)':
            embed.add_field(name='Observing Mode', value=data['observing_mode'])
        if data['allocated_time']:
            embed.add_field(name='Allocated Time', value=data['allocated_time'])
        if data['telescope_name']:
            embed.add_field(name='Telescope', value=data['telescope_name'])
        if data['instrument_name']:
            embed.add_field(name='Instrument', value=data['instrument_name'])
        if data['investigators_list']:
            embed.add_field(name='Investigators', value=data['investigators_list'])
        await ctx.send(embed=embed)

    @data.command(name='hst')
    async def data_hst(self, ctx, proposal_id: str):
        """Hubble Space Telescope (HST)
        https://archive.stsci.edu/hst/
        """
        url = f'https://api.arcsecond.io/archives/HST/{proposal_id}/summary/'
        async with ctx.session.get(url, params={'format': 'json'}) as resp:
            if resp.status == 404:
                return await ctx.reply(':no_entry: Error: Not found.')
            data = await resp.json()
        # TODO: Include allocation?, pi_institution?, programme_type_auxiliary?, programme_status?, related_programmes?
        embed = discord.Embed(title=data['title'], description=data['abstract'])
        if data['cycle']: embed.add_field(name='Cycle', value=data['cycle'])
        if data['principal_investigator']:
            embed.add_field(name='Principal Investigator', value=data['principal_investigator'])
        if data['programme_type'] and data['programme_type'] != '(Undefined)':
            embed.add_field(name='Proposal Type', value=data['programme_type'])
        await ctx.send(embed=embed)

    @astronomy.command()
    async def exoplanet(self, ctx, *, exoplanet: str):
        """Exoplanets"""
        # TODO: list?
        url = 'https://api.arcsecond.io/exoplanets/{}'.format(exoplanet)
        async with ctx.session.get(url, params={'format': 'json'}) as resp:
            if resp.status in (404, 500):
                await ctx.reply(':no_entry: Error')
                return
            data = await resp.json()
        # TODO: Include mass?, radius?, bibcodes?, omega_angle?, anomaly_angle?, angular_distance?,
        #  time_radial_velocity_zero?, hottest_point_longitude?, surface_gravity?, mass_detection_method?,
        #  radius_detection_method?
        # TODO: handle one of error_min or error_max, but not the other? (SWEEPS-11)
        # TODO: Improve efficiency with for loop?
        embed = discord.Embed(title=data['name'])
        embed.add_field(name='System', value=data['coordinates']['system'])
        if data['coordinates']['right_ascension']:
            value = data['coordinates']['right_ascension']
            if data['coordinates']['right_ascension_units'] == 'degrees':
                value += '°'
            else:
                value += f' {data["coordinates"]["right_ascension_units"]}'
            embed.add_field(name='Right Ascension', value=value)
        if data['coordinates']['declination']:
            value = data['coordinates']['declination']
            if data['coordinates']['declination_units'] == 'degrees':
                value += '°'
            else:
                value += f' {data["coordinates"]["declination_units"]}'
            embed.add_field(name='Declination', value=value)

        # Inclination
        inclination = ''
        if data['inclination']['value']:
            inclination += str(data['inclination']['value'])
        if data['inclination']['error_min'] or data['inclination']['error_max']:
            if data['inclination']['error_min'] == data['inclination']['error_max']:
                inclination += '±' + str(data['inclination']['error_min'])
            else:
                inclination += '(-{0[error_min]}/+{0[error_max]})'.format(data['inclination'])
        if data['inclination']['value']:
            inclination += data['inclination']['unit']
        if inclination:
            embed.add_field(name='Inclination', value=inclination)

        # Semi-major axis
        semi_major_axis = ''
        if data['semi_major_axis']['value']:
            semi_major_axis += str(data['semi_major_axis']['value'])
        if data['semi_major_axis']['error_min'] or data['semi_major_axis']['error_max']:
            if data['semi_major_axis']['error_min'] == data['semi_major_axis']['error_max']:
                semi_major_axis += '±' + str(data['semi_major_axis']['error_min'])
            else:
                semi_major_axis += '(-{0[error_min]}/+{0[error_max]})'.format(data['semi_major_axis'])
        if data['semi_major_axis']['value']:
            semi_major_axis += ' AU' if data['semi_major_axis']['unit'] == 'astronomical unit' \
                else f' {data["semi_major_axis"]["unit"]}'
        if semi_major_axis:
            embed.add_field(name='Semi-Major Axis', value=semi_major_axis)

        # Orbital Period
        # TODO: include orbital_period error_max + error_min?
        if data['orbital_period']['value']:
            embed.add_field(name='Orbital Period',
                            value=f'{data["orbital_period"]["value"]} {data["orbital_period"]["unit"]}')

        # Eccentricity
        eccentricity = ''
        if data['eccentricity']['value']:
            eccentricity += str(data['eccentricity']['value'])
        if data['eccentricity']['error_min'] or data['eccentricity']['error_max']:
            if data['eccentricity']['error_min'] == data['eccentricity']['error_max']:
                eccentricity += '±' + str(data['eccentricity']['error_min'])
            else:
                eccentricity += '(-{0[error_min]}/+{0[error_max]})'.format(data['eccentricity'])
        if eccentricity:
            embed.add_field(name='Eccentricity', value=eccentricity)

        # Lambda angle
        # Spin-Orbit misalignment
        # Sky-projected angle between the planetary orbital spin and the stellar rotational spin
        lambda_angle = ''
        lambda_angle_data = data.get('lambda_angle') or {}
        if lambda_angle_data.get('value'):
            lambda_angle += str(lambda_angle_data['value'])
        if lambda_angle_data.get('error_min') or lambda_angle_data.get('error_max'):
            if lambda_angle_data.get('error_min') == lambda_angle_data.get('error_max'):
                lambda_angle += '±' + str(lambda_angle_data['error_min'])
            else:
                lambda_angle += '(-{0[error_min]}/+{0[error_max]})'.format(lambda_angle_data)
        if lambda_angle_data.get('value'):
            lambda_angle += lambda_angle_data['unit']
        if lambda_angle:
            embed.add_field(name='Spin-Orbit misalignment', value=lambda_angle)

        # Periastron time
        # https://exoplanetarchive.ipac.caltech.edu/docs/parhelp.html#Obs_Time_Periastron
        time_periastron = ''
        if data['time_perastron']['value']:
            time_periastron += str(data['time_periastron']['value'])
        if data['time_periastron']['error_min'] or data['time_periastron']['error_max']:
            if data['time_periastron']['error_min'] == data['time_periastron']['error_max']:
                time_periastron += '±' + str(data['time_periastron']['error_min'])
            else:
                time_periastron += '(-{0[error_min]}/+{0[error_max]})'.format(data['time_periastron'])  # Necessary?
        if time_periastron:
            embed.add_field(name='Periastron Time', value=time_periastron)

        # Conjunction time
        time_conjonction = ''
        time_conjonction_data = data.get('time_conjonction') or {}
        if time_conjonction_data.get('value'):
            time_conjonction += str(time_conjonction_data['value'])
        if time_conjonction_data.get('error_min') or time_conjonction_data.get('error_max'):
            if time_conjonction_data.get('error_min') == time_conjonction_data.get('error_max'):
                time_conjonction += '±' + str(time_conjonction_data['error_min'])
            else:
                time_conjonction += '(-{0[error_min]}/+{0[error_max]})'.format(time_conjonction_data)  # Necessary?
        if time_conjonction:
            embed.add_field(name='Conjunction Time', value=time_conjonction)

        # Primary transit
        # in Julian Days (JD)
        primary_transit = ''
        primary_transit_data = data.get('primary_transit') or {}
        if primary_transit_data.get('value'):
            primary_transit += str(primary_transit_data['value'])
        if primary_transit_data.get('error_min') or primary_transit_data.get('error_max'):
            if primary_transit_data.get('error_min') == primary_transit_data.get('error_max'):
                primary_transit += '±' + str(primary_transit_data['error_min'])
            else:
                primary_transit += '(-{0[error_min]}/+{0[error_max]}'.format(primary_transit_data)  # Necessary?
        if primary_transit:
            embed.add_field(name='Primary Transit', value=primary_transit)

        # Secondary transit
        # in Julian Days (JD)
        secondary_transit = ''
        secondary_transit_data = data.get('secondary_transit') or {}
        if secondary_transit_data.get('value'):
            secondary_transit += str(secondary_transit_data['value'])
        if secondary_transit_data.get('error_min') or secondary_transit_data.get('error_max'):
            if secondary_transit_data.get('error_min') == secondary_transit_data.get('error_max'):
                secondary_transit += '±' + str(secondary_transit_data['error_min'])
            else:
                secondary_transit += '(-{0[error_min]}/+{0[error_max]})'.format(secondary_transit_data)
        if secondary_transit:
            embed.add_field(name='Secondary Transit', value=secondary_transit)

        # Impact parameter
        impact_parameter = ''
        impact_parameter_data = data.get('impact_parameter') or {}
        if impact_parameter_data.get('value'):
            impact_parameter += str(impact_parameter_data['value'])
        if impact_parameter_data.get('error_min') or impact_parameter_data.get('error_max'):
            if impact_parameter_data.get('error_min') == impact_parameter_data.get('error_max'):
                impact_parameter += '±' + str(impact_parameter_data['error_min'])
            else:
                impact_parameter += '(-{0[error_min]}/+{0[error_max]})'.format(impact_parameter_data)  # Necessary?
        if impact_parameter_data.get('value'):
            impact_parameter += impact_parameter_data['unit']
        if impact_parameter:
            embed.add_field(name='Impact Parameter', value=impact_parameter)

        # Radial velocity semi-amplitude
        velocity_semiamplitude = ''
        if data['velocity_semiamplitude']['value']:
            velocity_semiamplitude += str(data['velocity_semiamplitude']['value'])
        if data['velocity_semiamplitude']['error_min'] or data['velocity_semiamplitude']['error_max']:
            if data['velocity_semiamplitude']['error_min'] == data['velocity_semiamplitude']['error_max']:
                velocity_semiamplitude += '±' + str(data['velocity_semiamplitude']['error_min'])
            else:
                velocity_semiamplitude += '(-{0[error_min]}/+{0[error_max]})'.format(data['velocity_semiamplitude'])
                # Necessary?
        if data['velocity_semiamplitude']['value']:
            velocity_semiamplitude += f' {data["velocity_semiamplitude"]["unit"]}'
        if velocity_semiamplitude:
            embed.add_field(name='Radial Velocity Semi-Amplitude', value=velocity_semiamplitude)

        # Calculated Temperature
        calculated_temperature = ''
        calculated_temperature_data = data.get('calculated_temperature') or {}
        if calculated_temperature_data.get('value'):
            calculated_temperature += str(calculated_temperature_data['value'])
        if calculated_temperature_data.get('error_min') or calculated_temperature_data.get('error_max'):
            if calculated_temperature_data.get('error_min') == calculated_temperature_data.get('error_max'):
                calculated_temperature += '±' + str(calculated_temperature_data['error_min'])
            else:
                calculated_temperature += '(-{0[error_min]}/+{0[error_max]})'.format(calculated_temperature_data)
                # Necessary?
        if calculated_temperature_data.get('value'):
            calculated_temperature += 'K' if calculated_temperature_data.get('unit') == 'Kelvin' \
                else f' {calculated_temperature_data.get("unit")}'
        if calculated_temperature:
            embed.add_field(name='Calculated Temperature', value=calculated_temperature)

        # Measured Temperature
        # TODO: include measured_temperature error_max + error_min?
        measured_temperature_data = data.get('measured_temperature') or {}
        if measured_temperature_data.get('value'):
            v = f'{measured_temperature_data["value"]} ' \
                f'{"K" if measured_temperature_data.get("unit") == "Kelvin" else measured_temperature_data.get("unit")}'
            embed.add_field(name='Measured Temperature', value=v)

        # Geometric Albedo
        # TODO: include geometric_albedo error_max + error_min?
        if data['geometric_albedo']['value']:
            embed.add_field(name='Geometric Albedo', value=f"{data['geometric_albedo']['value']}")

        # Detection method
        if data['detection_method'] != 'Unknown':
            embed.add_field(name='Detection Method', value=data['detection_method'])

        # Parent star
        parent_star_data = data.get('parent_star') or {}
        if parent_star_data.get('name'):
            embed.add_field(name='Parent Star', value=parent_star_data['name'])
        elif parent_star_data.get('url'):
            async with self.bot.session.get(parent_star_data['url']) as resp:
                parent_star_data = await resp.json()
            embed.add_field(name='Parent Star', value=parent_star_data['name'])

        await ctx.send(embed=embed)

    @astronomy.command(aliases=['international_space_station', 'internationalspacestation'])
    async def iss(self, ctx, latitude: float = 0.0, longitude: float = 0.0):
        """Current location of the International Space Station (ISS).

        Enter a latitude and longitude to compute an estimate of the next time the ISS will be overhead.
        Overhead is defined as 10° in elevation for the observer at an altitude of 100m.
        """
        if latitude and longitude:
            url = 'http://api.open-notify.org/iss-pass.json'
            params = {'n': 1, 'lat': str(latitude), 'lon': str(longitude)}
            async with ctx.session.get(url, params=params) as resp:
                if resp.status == 500:
                    return await ctx.reply(':no_entry: Error')
                data = await resp.json()
            if data['message'] == 'failure':
                return await ctx.reply(f':no_entry: Error: {data["reason"]}')
            duration = duration_to_string(datetime.timedelta(seconds=data['response'][0]['duration']))
            timestamp = datetime.datetime.utcfromtimestamp(data['response'][0]['risetime'])
            embed = discord.Embed(timestamp=timestamp)
            embed.add_field(name='Duration', value=duration)
            embed.set_footer(text='Rise Time')
            await ctx.send(embed=embed)
        else:
            url = 'http://api.open-notify.org/iss-now.json'
            async with ctx.session.get(url) as resp:
                data = await resp.json()
            latitude = data['iss_position']['latitude']
            longitude = data['iss_position']['longitude']
            timestamp = datetime.datetime.utcfromtimestamp(data['timestamp'])
            map_icon = 'https://i.imgur.com/KPfeEcc.png'  # 64x64 satellite emoji png
            embed = discord.Embed(title='Current ISS Position', timestamp=timestamp,
                                  url=f'https://www.google.com/maps/place/{latitude},{longitude}/@{latitude},{longitude},3.6z')
            embed.set_thumbnail(url=map_icon)
            embed.add_field(name='Latitude', value=latitude)
            embed.add_field(name='Longitude', value=longitude)
            await ctx.send(embed=embed)

    @astronomy.command(name='object')
    async def astronomy_object(self, ctx, *, object: str):
        """WIP"""
        # https://api.arcsecond.io/objects/alpha%20centauri/
        ...

    @astronomy.command()
    async def observatory(self, ctx, *, observatory: str):
        """Observatories
        Observing sites on Earth
        """
        # TODO: list?
        async with ctx.session.get('https://api.arcsecond.io/observingsites/', params={'format', 'json'}) as resp:
            data = await resp.json()
        embed = discord.Embed()
        for _observatory in data:
            if observatory.lower() in _observatory['name'].lower():
                embed.title = _observatory['name']
                embed.url = _observatory['homepage_url'] or discord.Embed.Empty
                embed.add_field(name='Latitude', value=_observatory['coordinates']['latitude'])
                embed.add_field(name='Longitude', value=_observatory['coordinates']['longitude'])
                embed.add_field(name='Height', value=f'{_observatory["coordinates"]["height"]}m')
                embed.add_field(name='Continent', value=_observatory['address']['continent'])
                embed.add_field(name='Country', value=_observatory['address']['country'])
                time_zone = f'{_observatory["address"]["time_zone_name"]}\n({_observatory["address"]["time_zone"]})'
                if len(time_zone) <= 22:
                    time_zone = time_zone.replace('\n', ' ')  # 22: embed field value without offset
                embed.add_field(name='Time Zone', value=time_zone)
                if _observatory['IAUCode']:
                    embed.add_field(name='IAU Code', value=_observatory['IAUCode'])
                telescopes = []
                for telescope in _observatory['telescopes']:
                    async with ctx.session.get(telescope) as resp:
                        telescope_data = await resp.json()
                    telescopes.append(telescope_data['name'])
                if telescopes:
                    embed.add_field(name='Telescopes', value='\n'.join(telescopes))
                await ctx.send(embed=embed)
                return
        await ctx.reply(':no_entry: Observatory not found.')

    @astronomy.command()
    async def people(self, ctx):
        """People currently in space."""
        # TODO: add input/search option
        async with ctx.session.get('http://api.open-notify.org/astros.json') as resp:
            data = await resp.json()
        embed = discord.Embed(description='\n'.join(f'{person["name"]} ({person["craft"]})'
                                                    for person in data['people']),
                              title=f'People Currently In Space ({data["number"]})')
        await ctx.send(embed=embed)

    @astronomy.command()
    async def publication(self, ctx, *, bibcode: str):
        """Publications."""
        params = {'format', 'json'}
        async with ctx.session.get(f'https://api.arcsecond.io/publications/{bibcode}/', params=params) as resp:
            data = await resp.json()
        if not data:
            await ctx.reply(':no_entry: Publication not found.')
            return
        if isinstance(data, list):
            data = data[0]
        embed = discord.Embed(title=data['title'])
        embed.add_field(name='Journal', value=data['journal'])
        embed.add_field(name='Year', value=data['year'])
        embed.add_field(name='Authors', value=data['authors'])
        await ctx.send(embed=embed)

    @astronomy.group(invoke_without_command=True)
    async def telegram(self, ctx):
        """Quick publications, often related to ongoing events occurring in the sky."""
        await ctx.send_help(ctx.command)

    @telegram.command(name='atel', aliases=['astronomerstelegram'])
    async def telegram_atel(self, ctx, number: int):
        """The Astronomer's Telegram
        http://www.astronomerstelegram.org/
        """
        # TODO: use textwrap
        params = {'format': 'json'}
        async with ctx.session.get(f'https://api.arcsecond.io/telegrams/ATel/{number}/', params=params) as resp:
            if resp.status == 500:
                await ctx.reply(':no_entry: Error')
                return
            data = await resp.json()
        # TODO: include credential_certification?, authors?, referring_telegrams?, external_links?
        description = data['content'].replace('\n', ' ')
        if len(description) > 1000:
            description = description[:1000] + '...'
        embed = discord.Embed(title=data['title'], url=f'http://www.astronomerstelegram.org/?read={number}',
                              description=description)
        if len(data['subjects']) > 1 or data['subjects'][0] != 'Undefined':
            embed.add_field(name='Subjects', value=', '.join(sorted(data['subjects'])))
        related = ['[{0}](http://www.astronomerstelegram.org/?read={0})'.format(related_telegram)
                   for related_telegram in sorted(data['related_telegrams'])]
        if related:
            for i in range(0, len(related), 18):
                embed.add_field(name='Related Telegrams', value=', '.join(related[i:i + 18]))
        if data['detected_objects']:
            embed.add_field(name='Detected Objects', value=', '.join(sorted(data['detected_objects'])))
        await ctx.send(embed=embed)

    @telegram.command(name='gcn', aliases=['circulars'])
    async def telegram_gcn(self, ctx, number: str):
        """GCN Circulars
        https://gcn.gsfc.nasa.gov/
        """
        # TODO: Use textwrap
        url = f'https://api.arcsecond.io/telegrams/GCN/Circulars/{number}/'
        params = {'format': 'json'}
        async with ctx.session.get(url, params=params) as resp:
            if resp.status in (404, 500):
                return await ctx.reply(':no_entry: Error')
            data = await resp.json()
        # TODO: include submitter?, authors?, related_circulars?, external_links?
        description = re.sub('([^\n])\n([^\n])', r'\1 \2', data['content'])
        description = re.sub(r'\n\s*\n', '\n', description)
        if len(description) > 1000:
            description = description[:1000] + '...'
        description = f'```\n{description}\n```'
        embed = discord.Embed(title=data['title'] or discord.Embed.Empty,
                              url=f'https://gcn.gsfc.nasa.gov/gcn3/{number}.gcn3',
                              description=description,
                              timestamp=dateutil.parser.parse(data['date']) if data['date'] else discord.Embed.Empty)
        await ctx.send(embed=embed)

    @astronomy.command(aliases=['instrument'])
    async def telescope(self, ctx, *, telescope: str):
        """Telescopes and instruments at observing sites on Earth."""
        # TODO: list?
        async with ctx.session.get('https://api.arcsecond.io/telescopes/', params={'format': 'json'}) as resp:
            data = await resp.json()
        embed = discord.Embed()
        for _telescope in data:
            if telescope.lower() in _telescope['name'].lower():
                embed.title = _telescope['name']
                async with ctx.session.get(_telescope['observing_site']) as resp:
                    observatory_data = await resp.json()
                embed.add_field(name='Observatory', value='[{0[name]}]({0[homepage_url]})'.format(observatory_data)
                                if observatory_data['homepage_url'] else observatory_data['name'])
                if _telescope['mounting'] != 'Unknown':
                    embed.add_field(name='Mounting', value=_telescope['mounting'])
                if _telescope['optical_design'] != 'Unknown':
                    embed.add_field(name='Optical Design', value=_telescope['optical_design'])
                properties = []
                if _telescope['has_active_optics']:
                    properties.append('Active Optics')
                if _telescope['has_adaptive_optics']:
                    properties.append('Adaptive Optics')
                if _telescope['has_laser_guide_star']:
                    properties.append('Laser Guide Star')
                if properties:
                    embed.add_field(name='Properties', value='\n'.join(properties))
                await ctx.send(embed=embed)
                return
        await ctx.reply(':no_entry: Telescope/Instrument not found.')

    async def cog_command_error(self, ctx, error):
        if isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.reply(error)


def setup(bot):
    bot.add_cog(Astronomy(bot))
