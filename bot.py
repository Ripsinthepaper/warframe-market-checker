import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

HEADERS = {
    "Accept": "application/json",
    "Language": "en",
    "Platform": "pc",
    "Origin": "https://warframe.market",
    "Referer": "https://warframe.market/",
    "User-Agent": "Mozilla/5.0"
}


# ==================================================
# WARFRAME MARKET FUNCTIONS
# ==================================================

def to_slug(name):
    return name.strip().lower().replace(" ", "_")


async def fetch_orders(session, slug):
    url = f"https://api.warframe.market/v2/orders/item/{slug}"

    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:

            if response.status != 200:
                return None

            return await response.json()

    except Exception as e:
        print(f"Error fetching {slug}: {e}")
        return None


def extract_orders(data):
    if not data:
        return []

    orders = []

    for o in data.get("data", []):

        if o.get("type") != "sell":
            continue

        user = o.get("user", {})

        if user.get("status") != "ingame":
            continue

        orders.append({
            "price": int(o.get("platinum", 0)),
            "quantity": o.get("quantity", 1),
            "rank": o.get("rank", 0)
        })

    return orders


def get_activity_score(orders):
    return sum(o.get("quantity", 1) for o in orders)


def filter_max_rank(orders):
    if not orders:
        return orders

    max_rank = max(
        o.get("rank", 0)
        for o in orders
    )

    return [
        o for o in orders
        if o.get("rank", 0) == max_rank
    ]


def load_grouped(filename):

    grouped = defaultdict(list)
    faction = "Unknown"

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            if line.endswith(":"):
                faction = line[:-1]
                continue

            grouped[faction].append(line)

    return grouped


async def process_item(
    session,
    item,
    arcane=False
):

    slug = to_slug(item)

    data = await fetch_orders(
        session,
        slug
    )

    orders = extract_orders(data)

    if not orders:
        return None

    if arcane:
        orders = filter_max_rank(
            orders
        )

    cheapest = min(
        orders,
        key=lambda x: x["price"]
    )

    activity = get_activity_score(
        orders
    )

    return (
        item,
        cheapest["price"],
        activity
    )


async def get_results(
    items,
    arcane=False
):

    async with aiohttp.ClientSession() as session:

        tasks = [
            process_item(
                session,
                item,
                arcane
            )
            for item in items
        ]

        results = await asyncio.gather(
            *tasks
        )

    results = [
        r for r in results
        if r is not None
    ]

    results.sort(
        key=lambda x: x[1],
        reverse=True
    )

    return results


# ==================================================
# DISCORD UI
# ==================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


class FactionDropdown(discord.ui.Select):

    def __init__(self, grouped, arcane):

        self.grouped = grouped
        self.arcane = arcane

        options = [
            discord.SelectOption(
                label=faction,
                value=faction
            )
            for faction in grouped.keys()
        ]

        super().__init__(
            placeholder="Choose a faction...",
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.defer()

        faction = self.values[0]

        items = self.grouped[faction]

        results = await get_results(
            items,
            self.arcane
        )

        embed = discord.Embed(
            title=faction,
            color=discord.Color.gold()
        )

        if not results:

            embed.description = (
                "No market data found."
            )

        else:

            for item, price, activity in results[:25]:

                embed.add_field(
                    name=item,
                    value=(
                        f"<:601277029458903040:1510971000911695883> {price}p\n"
                        f":chart_with_upwards_trend: Volume: {activity}"
                    ),
                    inline=False
                )

        await interaction.followup.send(
            embed=embed
        )


class FactionView(discord.ui.View):

    def __init__(
        self,
        grouped,
        arcane
    ):

        super().__init__(timeout=300)

        self.add_item(
            FactionDropdown(
                grouped,
                arcane
            )
        )


class MainMenu(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="Mods",
        style=discord.ButtonStyle.primary
    )
    async def mods_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        grouped = load_grouped("mods.txt")

        await interaction.response.send_message(
            "Select a faction:",
            view=FactionView(grouped, False),
            ephemeral=True
        )

    @discord.ui.button(
        label="Arcanes",
        style=discord.ButtonStyle.success
    )
    async def arcanes_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        grouped = load_grouped("arcanes.txt")

        await interaction.response.send_message(
            "Select a faction:",
            view=FactionView(grouped, True),
            ephemeral=True
        )

    @discord.ui.button(
        label="Imprints",
        style=discord.ButtonStyle.danger
    )
    async def imprints_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        grouped = load_grouped("imprints.txt")

        await interaction.response.send_message(
            "Select a faction:",
            view=FactionView(grouped, False),
            ephemeral=True
        )

    @discord.ui.button(
        label="Both",
        style=discord.ButtonStyle.secondary
    )
    async def both_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "Choose Mods or Arcanes for now.\nCombined mode will be added later.",
            ephemeral=True
        )


# ==================================================
# SLASH COMMAND
# ==================================================

@bot.tree.command(
    name="market",
    description="Open Warframe Market UI"
)
async def market(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="Warframe Market Checker",
        description=(
            "Select what you want to browse."
        ),
        color=discord.Color.blue()
    )

    await interaction.response.send_message(
        embed=embed,
        view=MainMenu()
    )


# ==================================================
# STARTUP
# ==================================================

@bot.event
async def on_ready():

    try:
        synced = await bot.tree.sync()

        print(
            f"Synced {len(synced)} commands"
        )

    except Exception as e:
        print(
            f"Command sync failed: {e}"
        )

    print(
        f"Logged in as {bot.user}"
    )


bot.run(TOKEN)
