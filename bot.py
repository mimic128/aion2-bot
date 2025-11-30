import os
import discord
from discord.ext import commands
import json
import difflib

TOKEN = os.getenv("TOKEN")
COMMAND_PREFIX = "!"

with open("aion2_data.json", "r", encoding="utf-8") as f:
    SPOTS = json.load(f)

# ✅ 채집물 / 거점 이름 목록 준비
VALID_ITEMS = set()
for items_list in SPOTS.values():
    for item in items_list:
        VALID_ITEMS.add(item)

VALID_SPOT_NAMES = list(SPOTS.keys())


# ✅ 채집물 이름 자동 보정 (오타/반쪽 이름)
def normalize_item_name(name: str):
    name = name.strip()
    if not name:
        return None, None

    # 1) 정확히 일치하면 그대로
    if name in VALID_ITEMS:
        return name, False

    # 2) 앞부분이 일치하는 채집물 찾기 (줄임말 자동완성)
    #    예: "오리하" → "오리하르콘", "이그" → "이그드라실"
    prefix_matches = [v for v in VALID_ITEMS if v.startswith(name)]
    if len(prefix_matches) == 1:
        return prefix_matches[0], True

    # 3) 철자 살짝 틀린 경우(오타) → 유사도 기반 매칭
    candidates = difflib.get_close_matches(name, list(VALID_ITEMS), n=1, cutoff=0.5)
    if candidates:
        corrected = candidates[0]
        return corrected, True

    # 4) 진짜로 아무 것도 못 찾았을 때
    return None, None


# ✅ 거점 이름 자동 보정
def normalize_spot_name(name: str):
    name = name.strip()
    if not name:
        return None, None

    if name in SPOTS:
        return name, None

    candidates = difflib.get_close_matches(name, VALID_SPOT_NAMES, n=1, cutoff=0.6)
    if candidates:
        corrected = candidates[0]
        return corrected, corrected != name

    return None, None


def find_spots_any(item: str):
    item = item.strip()
    result = []
    for spot_name, items in SPOTS.items():
        if item in items:
            result.append(spot_name)
    return result


def find_spots_all(items):
    items = list({i.strip() for i in items if i.strip()})
    result = []
    for spot_name, spot_items in SPOTS.items():
        if all(i in spot_items for i in items):
            result.append(spot_name)
    return result


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)


# ✅ 공용 사용법 Embed 생성 함수
def make_usage_embed():
    embed = discord.Embed(
        title="📖 사용법 - 채집 & 거점 검색",
        description=(
            "채집물 이름이나 거점 이름으로 아이온2 채집 정보를 검색할 수 있어요.\n\n"
            "**채집물 검색 예시**\n"
            "• `!채집 오드`\n"
            "• `!채집 오드, 안젤리카`\n"
            "→ 입력한 채집물을 모두 가진 거점을 찾아줘요."
        ),
        color=0xF1C40F,
    )
    embed.add_field(
        name="자동완성 / 오타 보정",
        value=(
            "`오리하` → **오리하르콘**, `이그` → **이그드라실** 처럼 앞부분만 써도 인식해요.\n"
            "조금 틀려도 비슷한 채집물로 인식하고, 완전 다른 이름이면\n"
            "`그런 채집물은 없는데..` 라고 알려줄게요."
        ),
        inline=False,
    )
    embed.add_field(
        name="거점 검색 예시",
        value=(
            "`!거점 엘룬강 늪지`\n"
            "`!거점 새벽의 레기온 기지`\n"
            "→ 해당 거점에서 채집 가능한 채집물 목록을 보여줘요."
        ),
        inline=False,
    )
    embed.set_footer(text="언제든지 `!사용법` 또는 `!도움말`로 이 안내를 다시 볼 수 있어요.")
    return embed


@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user}")


@bot.command(name="채집")
async def gather_command(ctx, *, query: str):
    # "오드, 안젤리카" → ["오드", "안젤리카"]
    raw_items = [x.strip() for x in query.split(",") if x.strip()]

    # ✅ 인자가 없으면 사용법 Embed 보여주기
    if not raw_items:
        embed = make_usage_embed()
        await ctx.send(embed=embed)
        return

    normalized_items = []
    invalid_items = []
    corrections = {}

    # ✅ 각 채집물 이름 오타/자동보정 처리
    for raw in raw_items:
        norm, changed = normalize_item_name(raw)
        if not norm:
            invalid_items.append(raw)
        else:
            normalized_items.append(norm)
            if changed:
                corrections[raw] = norm

    # ✅ 목록에 아예 없는 채집물 있을 때
    if invalid_items:
        invalid_label = ", ".join(invalid_items)
        embed = discord.Embed(
            title=f"🌿 {invalid_label}",
            description="🤔 그런 채집물은 없는데..\n채집물 이름을 다시 확인해주세요!",
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)
        return

    # ✅ 중복 제거 (보정 후 같은 이름이 된 경우 등)
    items = []
    seen = set()
    for it in normalized_items:
        if it not in seen:
            seen.add(it)
            items.append(it)

    # 🔎 보정된 이름이 있다면 footer에 안내
    def apply_footer(embed: discord.Embed):
        if corrections:
            mapping = ", ".join(f"{old} → {new}" for old, new in corrections.items())
            embed.set_footer(text=f"입력한 이름을 이렇게 인식했어요: {mapping}")
        return embed

    # ✅ 채집물 1개 검색
    if len(items) == 1:
        item = items[0]
        spots = find_spots_any(item)

        if not spots:
            embed = discord.Embed(
                title=f"🌿 {item}",
                description="😢 해당 채집물이 있는 거점을 찾지 못했습니다.",
                color=0xE67E22,
            )
            embed = apply_footer(embed)
            await ctx.send(embed=embed)
            return

        spot_lines = "\n".join(f"✨ {s}" for s in spots)
        desc = (
            "채집물이 있는 거점은 아래와 같습니다!\n\n"
            f"{spot_lines}"
        )
        embed = discord.Embed(
            title=f"🌿 {item}",
            description=desc,
            color=0x2ECC71,
        )
        embed = apply_footer(embed)
        await ctx.send(embed=embed)

    # ✅ 채집물 2개 이상(교집합) 검색
    else:
        spots = find_spots_all(items)
        items_label = " + ".join(items)

        if not spots:
            embed = discord.Embed(
                title=f"🌿 {items_label}",
                description="😢 입력한 채집물을 모두 가진 거점은 없습니다.",
                color=0xE67E22,
            )
            embed = apply_footer(embed)
            await ctx.send(embed=embed)
            return

        spot_lines = "\n".join(f"✨ {s}" for s in spots)
        desc = (
            "모두 있는 거점은 아래와 같습니다!\n\n"
            f"{spot_lines}"
        )
        embed = discord.Embed(
            title=f"🌿 {items_label}",
            description=desc,
            color=0x3498DB,
        )
        embed = apply_footer(embed)
        await ctx.send(embed=embed)


# ✅ 거점 → 채집물 역검색: !거점 엘룬강 늪지
@bot.command(name="거점")
async def spot_command(ctx, *, spot_query: str):
    spot_name, changed = normalize_spot_name(spot_query)

    # 없는 거점 이름
    if not spot_name:
        embed = discord.Embed(
            title=f"📍 {spot_query}",
            description="🤔 그런 거점은 없는데..\n거점 이름을 다시 확인해주세요!",
            color=0xE74C3C,
        )
        await ctx.send(embed=embed)
        return

    items = SPOTS[spot_name]
    item_lines = "\n".join(f"🌿 {i}" for i in items)
    desc = (
        "해당 거점에서 채집할 수 있는 채집물 목록입니다.\n\n"
        f"{item_lines}"
    )

    embed = discord.Embed(
        title=f"📍 {spot_name}",
        description=desc,
        color=0x9B59B6,
    )

    if changed:
        embed.set_footer(text=f"입력한 이름 '{spot_query}' 를(을) '{spot_name}' 로 인식했어요.")

    await ctx.send(embed=embed)


# ✅ 언제든지 사용법 보기: !사용법 / !도움말
@bot.command(name="사용법", aliases=["도움말"])
async def usage_command(ctx):
    embed = make_usage_embed()
    await ctx.send(embed=embed)


bot.run(TOKEN)
