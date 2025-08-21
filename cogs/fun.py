# cogs/fun.py
import discord
from discord.ext import commands
import random
import asyncio
import database as db
from .utils import checks
import math
from discord import app_commands

# =============================================================
# NEW/UPDATED VIEWS AND MODALS
# =============================================================


class CreateNewLobbyView(discord.ui.View):
    """View chung để tạo lại các lobby game nhiều người chơi."""

    def __init__(self, cog, original_ctx, game_name: str, bet_amount: int = 0):
        super().__init__(timeout=180.0)
        self.cog, self.original_ctx, self.game_name, self.bet_amount = cog, original_ctx, game_name, bet_amount

    async def interaction_check(
        self, interaction: discord.Interaction) -> bool: return True

    @discord.ui.button(label="Tạo Bàn Mới", style=discord.ButtonStyle.green, emoji="➕")
    async def new_lobby_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Sử dụng lại context gốc để đảm bảo ổn định
        # và cập nhật người tương tác mới
        new_ctx = self.original_ctx
        new_ctx.author = interaction.user
        new_ctx.interaction = interaction

        # 2. Defer và xóa tin nhắn cũ
        # Phải defer trước khi xóa để tránh lỗi "Interaction failed"
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except (discord.NotFound, discord.HTTPException):
            pass  # Bỏ qua nếu tin nhắn đã bị xóa

        # 3. Lấy các cog một cách tường minh, không dựa vào self.cog nữa
        # =============================================================
        # <<< SỬA LỖI TẠI ĐÂY >>>
        # Thay self.bot bằng self.cog.bot
        fun_cog = self.cog.bot.get_cog('Fun')
        blackjack_cog = self.cog.bot.get_cog('Blackjack')
        # =============================================================

        # Kiểm tra xem các cog có tồn tại không
        if not fun_cog or not blackjack_cog:
            # Gửi tin nhắn lỗi nếu không tìm thấy cog cần thiết
            await interaction.followup.send("Lỗi: Không thể tìm thấy module game cần thiết. Vui lòng liên hệ admin.", ephemeral=True)
            return

        # 4. Tạo map lệnh từ các cog đã lấy được
        game_map = {
            'flip': fun_cog.flip,
            'duangua': fun_cog.horse_race,
            'taixiu': fun_cog.tai_xiu_table,
            'poker': fun_cog.poker_table,
            'blackjack': blackjack_cog.blackjack_table
        }

        # 5. Gọi lệnh tương ứng với logic đã được dọn dẹp
        if self.game_name in game_map:
            command_to_call = game_map[self.game_name]

            # Đua ngựa là game duy nhất không có tiền cược trong lệnh
            if self.game_name == 'duangua':
                await command_to_call(new_ctx)
            else:
                # Tất cả các game còn lại đều cần tham số bet_amount
                await command_to_call(new_ctx, self.bet_amount)
        else:
            await interaction.followup.send(f"Lỗi: Không tìm thấy game có tên '{self.game_name}'.", ephemeral=True)


class SlotsRebetModal(discord.ui.Modal):
    def __init__(self, cog, original_ctx):
        super().__init__(title="Bắt Đầu Ván Slots Mới")
        self.cog = cog
        self.original_ctx = original_ctx
        self.bet_amount_input = discord.ui.TextInput(
            label="Nhập số tiền cược cho ván mới",
            placeholder="Ví dụ: 1000",
            required=True
        )
        self.add_item(self.bet_amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.message.delete()
        await interaction.response.defer()
        try:
            bet_amount = int(self.bet_amount_input.value)
            if bet_amount <= 0:
                raise ValueError
        except ValueError:
            return await interaction.followup.send("Vui lòng nhập một số tiền hợp lệ.", ephemeral=True)
        await self.cog.slots(self.original_ctx, bet_amount)


class SlotsPlayAgainView(discord.ui.View):
    def __init__(self, cog, original_ctx):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.original_ctx = original_ctx

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id == self.original_ctx.author.id:
            return True
        await interaction.response.send_message("Đây không phải trò chơi của bạn!", ephemeral=True)
        return False

    @discord.ui.button(label="Chơi Ván Mới", style=discord.ButtonStyle.green, emoji="🔁")
    async def new_game_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SlotsRebetModal(self.cog, self.original_ctx))

    @discord.ui.button(label="Đóng", style=discord.ButtonStyle.red, emoji="✖️")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()


class RebetModal(discord.ui.Modal):
    """Modal chung để nhập lại tiền cược cho các game solo."""

    def __init__(self, title: str, cog, original_ctx, game_name: str):
        super().__init__(title=title)
        self.cog, self.original_ctx, self.game_name = cog, original_ctx, game_name
        self.bet_amount_input = discord.ui.TextInput(
            label="Nhập số tiền cược cho ván mới", placeholder="1000", required=True)
        self.add_item(self.bet_amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.message.delete()
        await interaction.response.defer()
        try:
            bet_amount = int(self.bet_amount_input.value)
            if bet_amount <= 0:
                raise ValueError
        except ValueError:
            return await interaction.followup.send("Vui lòng nhập một số tiền hợp lệ.", ephemeral=True)
        if self.game_name == 'slots':
            await self.cog.slots(self.original_ctx, bet_amount)
        elif self.game_name == 'coin':
            await self.cog.coin(self.original_ctx, bet_amount)


class PlayAgainView(discord.ui.View):
    """View chung cho các game solo có cược."""

    def __init__(self, cog, original_ctx, game_name: str, modal_title: str):
        super().__init__(timeout=180.0)
        self.cog, self.original_ctx, self.game_name, self.modal_title = cog, original_ctx, game_name, modal_title

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id == self.original_ctx.author.id:
            return True
        await interaction.response.send_message("Đây không phải trò chơi của bạn!", ephemeral=True)
        return False

    @discord.ui.button(label="Chơi Ván Mới", style=discord.ButtonStyle.green, emoji="🔁")
    async def new_game_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RebetModal(self.modal_title, self.cog, self.original_ctx, self.game_name))

    @discord.ui.button(label="Đóng", style=discord.ButtonStyle.red, emoji="✖️")
    async def close_button(self, interaction: discord.Interaction,
                           button: discord.ui.Button): await interaction.message.delete()


class CoinNoBetView(discord.ui.View):
    """View riêng cho /coin không cược."""

    def __init__(self, cog, original_ctx):
        super().__init__(timeout=180.0)
        self.cog, self.original_ctx = cog, original_ctx

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id == self.original_ctx.author.id:
            return True
        await interaction.response.send_message("Đây không phải trò chơi của bạn!", ephemeral=True)
        return False

    @discord.ui.button(label="Tung Lại", style=discord.ButtonStyle.primary, emoji="🪙")
    async def flip_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        await self.cog.coin(self.original_ctx, bet=0)


class RPSReplayView(discord.ui.View):
    """View để thách đấu lại hoặc đóng sau trận Oẳn tù tì."""

    def __init__(self, cog, original_ctx, opponent: discord.Member, bet_amount: int):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.original_ctx = original_ctx
        self.opponent = opponent
        self.bet_amount = bet_amount
        # Nút "Thách Đấu Lại" sẽ bị vô hiệu hóa nếu đây là trận không cược
        # và đối thủ đã rời server.
        if bet_amount == 0 and not self.original_ctx.guild.get_member(self.opponent.id):
            self.children[0].disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Chỉ người thách đấu gốc mới có thể nhấn "Thách đấu lại"
        if interaction.data['custom_id'] == "rematch_button" and interaction.user.id != self.original_ctx.author.id:
            await interaction.response.send_message("Chỉ người thách đấu ban đầu mới có thể bắt đầu lại.", ephemeral=True)
            return False
        # Ai cũng có thể nhấn nút "Đóng"
        return True

    @discord.ui.button(label="Thách Đấu Lại", style=discord.ButtonStyle.primary, emoji="⚔️", custom_id="rematch_button")
    async def rematch_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

        # Cập nhật lại context với người tương tác mới
        new_ctx = self.original_ctx
        new_ctx.author = interaction.user
        new_ctx.interaction = interaction

        # Gọi lại lệnh rps với các thông tin đã lưu
        await self.cog.rockpaperscissors(new_ctx, self.opponent, self.bet_amount)

    @discord.ui.button(label="Đóng", style=discord.ButtonStyle.red, emoji="✖️", custom_id="close_button")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
# =============================================================
# OTHER FUNCTIONS, VIEWS, AND MODALS
# =============================================================


def create_deck():
    suits, ranks = ["♠️", "♣️", "♥️", "♦️"], ["A", "2", "3",
                                              "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    deck = [(rank, suit) for rank in ranks for suit in suits]
    random.shuffle(deck)
    return deck


def score_hand(hand):
    if all(card[0] in ["J", "Q", "K"] for card in hand):
        return 10
    value = 0
    for card in hand:
        rank = card[0]
        if rank == "A":
            value += 1
        elif rank.isdigit():
            value += int(rank)
        elif rank in ["J", "Q", "K", "10"]:
            value += 10
    return value % 10


class ConfirmationView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=60.0)
        self.author = author
        self.confirmed = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Đây không phải là yêu cầu của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Chấp nhận", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="❌ Từ chối", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class CoinflipLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, bet_amount: int, cog):
        super().__init__(timeout=120.0)
        self.host, self.bet_amount, self.cog = host, bet_amount, cog
        self.players = {host}
        self.message = None
        self.original_ctx = None

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🪙 Bàn Cược Tung Đồng Xu - Cược {self.bet_amount:,} Coin",
                              description="Ai muốn thử vận may? Nhấn nút **Tham Gia**!", color=discord.Color.gold())
        player_list = "\n".join([p.mention for p in self.players])
        embed.add_field(
            name=f"Người chơi đã tham gia ({len(self.players)})", value=player_list or "Chưa có ai.")
        embed.set_footer(
            text=f"Chủ xị ({self.host.display_name}) có thể bắt đầu hoặc hủy.")
        return embed

    @discord.ui.button(label="Tham Gia", style=discord.ButtonStyle.green, emoji="🎟️")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            return await interaction.response.send_message("Bạn đã tham gia rồi!", ephemeral=True)
        user_data = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        if user_data['coins'] < self.bet_amount:
            return await interaction.response.send_message(f"Bạn không đủ **{self.bet_amount:,}** coin.", ephemeral=True)
        self.players.add(interaction.user)
        await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(label="Bắt Đầu", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị mới có thể bắt đầu.", ephemeral=True)
        if len(self.players) < 2:
            return await interaction.response.send_message("Cần ít nhất 2 người chơi.", ephemeral=True)
        for player in self.players:
            await db.update_coins(player.id, interaction.guild.id, -self.bet_amount)
        game_view = CoinflipGameView(
            list(self.players), self.bet_amount, self.cog, self.original_ctx)
        game_view.message = self.message
        await interaction.response.edit_message(embed=game_view.create_embed(), view=game_view)
        self.stop()

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.red, emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị mới có thể hủy.", ephemeral=True)
        embed = self.create_embed()
        embed.title = "[ĐÃ HỦY] " + embed.title
        embed.description = "Bàn cược đã được hủy."
        embed.color = discord.Color.dark_grey()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CoinflipGameView(discord.ui.View):
    def __init__(self, players: list[discord.Member], bet_amount: int, cog, original_ctx):
        super().__init__(timeout=60.0)
        self.players, self.bet_amount, self.cog, self.original_ctx = players, bet_amount, cog, original_ctx
        self.choices = {p.id: None for p in self.players}
        self.message = None

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🪙 Tung Đồng Xu - Mức cược {self.bet_amount:,} Coin", description="**Sấp hay Ngửa?**", color=discord.Color.yellow())
        status_lines = [
            f"{p.mention}: {'✅' if self.choices[p.id] else '🤔'}" for p in self.players]
        embed.add_field(name="Trạng thái", value="\n".join(status_lines))
        return embed

    async def resolve_game(self, interaction: discord.Interaction):
        self.stop()
        for c in self.children:
            c.disabled = True
        result = random.choice(["Sấp", "Ngửa"])
        winners = [p for p in self.players if self.choices[p.id] == result]
        losers = [p for p in self.players if self.choices[p.id]
                  != result and self.choices[p.id] is not None]
        embed = discord.Embed(
            title=f"Kết Quả: Đồng xu là **{result}**!", color=discord.Color.blue())
        embed.description = "\n".join(
            [f"{p.mention} chọn **{self.choices.get(p.id) or 'Không chọn'}**" for p in self.players])
        if not winners or not losers:
            embed.add_field(
                name="Kết quả", value="**HÒA NHAU!** Tiền cược đã được hoàn lại.")
            for p in self.players:
                await db.update_coins(p.id, interaction.guild.id, self.bet_amount)
        else:
            winnings = (self.bet_amount * len(losers) //
                        len(winners)) + self.bet_amount
            embed.add_field(
                name=f"🎉 Phe {result} thắng! 🎉", value=f"{', '.join(w.mention for w in winners)} nhận **{winnings:,}** coin mỗi người.")
            for winner in winners:
                await db.update_coins(winner.id, interaction.guild.id, winnings)
                await db.update_quest_progress(winner.id, interaction.guild.id, 'FLIP_WIN')

        new_lobby_view = CreateNewLobbyView(
            self.cog, self.original_ctx, 'flip', self.bet_amount)
        await interaction.message.edit(embed=embed, view=new_lobby_view)

    async def handle_choice(self, interaction: discord.Interaction, choice: str):
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(f"Bạn đã chọn **{choice}**!", ephemeral=True)
        await self.message.edit(embed=self.create_embed())
        if all(self.choices.values()):
            await self.resolve_game(interaction)

    @discord.ui.button(label="Sấp", emoji="💿")
    async def heads(self, interaction: discord.Interaction,
                    button: discord.ui.Button): await self.handle_choice(interaction, "Sấp")

    @discord.ui.button(label="Ngửa", emoji="🪙")
    async def tails(self, interaction: discord.Interaction,
                    button: discord.ui.Button): await self.handle_choice(interaction, "Ngửa")


class RPSGameView(discord.ui.View):
    def __init__(self, challenger, opponent):
        super().__init__(timeout=60.0)
        self.challenger, self.opponent = challenger, opponent
        self.choices = {challenger.id: None, opponent.id: None}
        self.CHOICE_EMOJIS = {"búa": "✊", "bao": "✋", "kéo": "✌️"}
        self.winner = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in [self.challenger.id, self.opponent.id]:
            await interaction.response.send_message("Đây không phải trận đấu của bạn!", ephemeral=True)
            return False
        if self.choices[interaction.user.id] is not None:
            await interaction.response.send_message("Bạn đã chọn rồi!", ephemeral=True)
            return False
        return True

    async def resolve_game(self, interaction: discord.Interaction):
        p1c, p2c = self.choices[self.challenger.id], self.choices[self.opponent.id]
        if p1c == p2c:
            self.winner = "hòa"
        elif (p1c, p2c) in [("búa", "kéo"), ("kéo", "bao"), ("bao", "búa")]:
            self.winner = self.challenger
        else:
            self.winner = self.opponent
        await interaction.message.delete()
        self.stop()

    async def handle_choice(self, interaction: discord.Interaction, choice: str):
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(f"Bạn đã chọn **{choice.title()}**!", ephemeral=True)
        if all(self.choices.values()):
            await self.resolve_game(interaction)

    @discord.ui.button(emoji="✊")
    async def rock(self, interaction: discord.Interaction,
                   button: discord.ui.Button): await self.handle_choice(interaction, "búa")

    @discord.ui.button(emoji="✋")
    async def paper(self, interaction: discord.Interaction,
                    button: discord.ui.Button): await self.handle_choice(interaction, "bao")

    @discord.ui.button(emoji="✌️")
    async def scissors(self, interaction: discord.Interaction,
                       button: discord.ui.Button): await self.handle_choice(interaction, "kéo")


class BetModal(discord.ui.Modal, title="Đặt Cược Đua Ngựa"):
    def __init__(self, view, horse_index: int):
        super().__init__()
        self.view, self.horse_index = view, horse_index
        self.horse_emoji = self.view.horses[self.horse_index]["emoji"]
        self.bet_amount_input = discord.ui.TextInput(
            label=f"Nhập số coin cược cho {self.horse_emoji}", placeholder="1000", required=True)
        self.add_item(self.bet_amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.bet_amount_input.value)
            assert bet_amount > 0
        except:
            return await interaction.response.send_message("Số tiền cược không hợp lệ.", ephemeral=True)
        user_data = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        if user_data['coins'] < bet_amount:
            return await interaction.response.send_message("Bạn không đủ coin.", ephemeral=True)

        user_bets = self.view.bets.setdefault(interaction.user, [])
        for bet in user_bets:
            if bet["horse"] == self.horse_index:
                bet["amount"] += bet_amount
                break
        else:
            user_bets.append({"horse": self.horse_index, "amount": bet_amount})

        await interaction.response.edit_message(embed=self.view.create_lobby_embed(), view=self.view)


class HorseRacingLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, cog):
        super().__init__(timeout=120.0)
        self.host, self.cog = host, cog
        self.message = None
        self.bets = {}
        self.original_ctx = None
        emojis = ["🐎", "🏇", "🦓", "🦄", "🐴", "🎠",
                  "♞", "🦒", "🐘", "🐖", "🐄", "🐂", "🐅", "🐆"]
        random.shuffle(emojis)
        self.horses = [{"emoji": e, "progress": 0} for e in emojis[:10]]

        for i, h in enumerate(self.horses):
            b = discord.ui.Button(
                label=h['emoji'], custom_id=f"bet_horse_{i}", row=i//5)
            b.callback = self.bet_button_callback
            self.add_item(b)

        start_btn = discord.ui.Button(
            label="Bắt đầu Đua!", style=discord.ButtonStyle.green, row=2)
        start_btn.callback = self.start_race_callback
        self.add_item(start_btn)

    async def bet_button_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BetModal(self, int(interaction.data["custom_id"].split("_")[-1])))

    def create_lobby_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🏇 Trường Đua Mở Cửa! 🏇",
                              description="Chọn chiến mã và đặt cược!", color=discord.Color.gold())
        bet_str = "\n".join(
            [f"{u.mention}: {', '.join([f'**{b['amount']:,}** cho {self.horses[b['horse']]['emoji']}' for b in bets])}" for u, bets in self.bets.items()])
        embed.add_field(name="📜 Cược Thủ",
                        value=bet_str or "Chưa có ai đặt cược.")
        embed.set_footer(
            text=f"Chủ xị ({self.host.display_name}) có thể bắt đầu.")
        return embed

    async def start_race_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị mới có thể bắt đầu.", ephemeral=True)
        if not self.bets:
            return await interaction.response.send_message("Cần ít nhất một người cược.", ephemeral=True)
        await interaction.response.defer()
        self.stop()
        await self.cog.start_the_race(self)


class TaixiuLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, bet_amount: int, cog):
        super().__init__(timeout=120.0)
        self.host, self.bet_amount, self.cog = host, bet_amount, cog
        self.players = {host}
        self.message = None
        self.original_ctx = None

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🎲 Bàn Cược Tài Xỉu - Cược {self.bet_amount:,} Coin 🎲",
                              description="Nhấn nút **Tham Gia**!", color=discord.Color.orange())
        embed.add_field(name=f"Người chơi ({len(self.players)})", value="\n".join(
            [p.mention for p in self.players]) or "Chưa có ai.")
        embed.set_footer(
            text=f"Chủ xị ({self.host.display_name}) có thể bắt đầu/hủy.")
        return embed

    @discord.ui.button(label="Tham Gia", emoji="🎟️")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            return await interaction.response.send_message("Bạn đã tham gia.", ephemeral=True)
        user_data = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        if user_data['coins'] < self.bet_amount:
            return await interaction.response.send_message(f"Không đủ **{self.bet_amount:,}** coin.", ephemeral=True)
        self.players.add(interaction.user)
        await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(label="Bắt Đầu", emoji="▶️")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị có thể bắt đầu.", ephemeral=True)
        if len(self.players) < 2:
            return await interaction.response.send_message("Cần ít nhất 2 người.", ephemeral=True)
        for p in self.players:
            await db.update_coins(p.id, interaction.guild.id, -self.bet_amount)
        game_view = TaixiuGameView(
            list(self.players), self.bet_amount, self.cog, self.original_ctx)
        game_view.message = self.message
        await interaction.response.edit_message(embed=game_view.create_embed(), view=game_view)
        self.stop()

    @discord.ui.button(label="Hủy", emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị có thể hủy.", ephemeral=True)
        embed = self.create_embed()
        embed.title = "[ĐÃ HỦY] " + embed.title
        embed.description = "Bàn cược đã hủy."
        embed.color = discord.Color.dark_grey()
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class TaixiuGameView(discord.ui.View):
    def __init__(self, players: list[discord.Member], bet_amount: int, cog, original_ctx):
        super().__init__(timeout=60.0)
        self.players, self.bet_amount, self.cog, self.original_ctx = players, bet_amount, cog, original_ctx
        self.choices = {p.id: None for p in self.players}
        self.message = None

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🎲 Tài Xỉu - Cược {self.bet_amount:,} Coin",
                              description="**Tài, Xỉu, hay Hòa?**", color=discord.Color.yellow())
        embed.add_field(name="Trạng thái", value="\n".join(
            [f"{p.mention}: {'✅' if self.choices[p.id] else '🤔'}" for p in self.players]))
        return embed

    async def resolve_game(self):
        self.stop()
        for c in self.children:
            c.disabled = True
        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        total = d1 + d2
        result_str = "Tài" if total > 7 else "Xỉu" if total < 7 else "Hòa"
        embed = discord.Embed(
            title=f"🎲 KẾT QUẢ: {d1}+{d2} = {total} ({result_str})! 🎲")
        details = ""
        for p in self.players:
            choice = self.choices.get(p.id)
            if not choice:
                details += f"{p.mention} không chọn và mất **{self.bet_amount:,}** coin.\n"
                continue
            if choice == result_str:
                payout = self.bet_amount * (5 if choice == "Hòa" else 2)
                await db.update_coins(p.id, p.guild.id, payout)
                details += f"🎉 {p.mention} cược **{choice}** và thắng **{payout:,}** coin!\n"
            else:
                details += f"💔 {p.mention} cược **{choice}** và thua **{self.bet_amount:,}** coin.\n"
        embed.description = details
        new_lobby_view = CreateNewLobbyView(
            self.cog, self.original_ctx, 'taixiu', self.bet_amount)
        await self.message.edit(embed=embed, view=new_lobby_view)

    async def handle_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id not in self.choices or self.choices[interaction.user.id]:
            return await interaction.response.send_message("Lỗi.", ephemeral=True)
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message(f"Bạn đã chọn **{choice}**!", ephemeral=True)
        await self.message.edit(embed=self.create_embed())
        if all(self.choices.values()):
            await self.resolve_game()

    @discord.ui.button(label="Tài (>7)")
    async def tai(self, interaction: discord.Interaction,
                  button: discord.ui.Button): await self.handle_choice(interaction, "Tài")

    @discord.ui.button(label="Hòa (=7)", style=discord.ButtonStyle.secondary)
    async def hoa(self, interaction: discord.Interaction,
                  button: discord.ui.Button): await self.handle_choice(interaction, "Hòa")

    @discord.ui.button(label="Xỉu (<7)")
    async def xiu(self, interaction: discord.Interaction,
                  button: discord.ui.Button): await self.handle_choice(interaction, "Xỉu")


class PokerRaiseModal(discord.ui.Modal, title="Tố Thêm"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.add_item(discord.ui.TextInput(
            label="Số tiền muốn tố thêm", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.children[0].value)
            assert amount > 0
        except:
            return await interaction.response.send_message("Số tiền không hợp lệ.", ephemeral=True)
        await self.view.handle_action(interaction, "raise", amount)


class PokerGameView(discord.ui.View):
    def __init__(self, players: list[discord.Member], initial_bet: int, message: discord.Message, cog, original_ctx):
        super().__init__(timeout=300.0)
        self.players, self.message, self.cog, self.original_ctx = players, message, cog, original_ctx
        self.deck = create_deck()
        self.dealer_hand = [self.deck.pop() for _ in range(3)]
        self.player_states = {p.id: {"hand": [self.deck.pop() for _ in range(
            3)], "status": "playing", "current_bet": initial_bet} for p in self.players}
        self.current_player_index = 0
        self.current_bet_to_match = initial_bet

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get('custom_id') == "view_hand_button":
            return interaction.user.id in self.player_states
        if not self.players or self.is_finished() or self.current_player_index >= len(self.players):
            return False
        if interaction.user.id != self.players[self.current_player_index].id:
            await interaction.response.send_message("Chưa đến lượt của bạn.", ephemeral=True)
            return False
        return True

    def create_game_embed(self, show_all_hands=False) -> discord.Embed:
        current_player = self.players[self.current_player_index] if self.current_player_index < len(
            self.players) else None
        embed = discord.Embed(
            title="🃏 Ván Bài 3 Lá 🃏", description=f"Đến lượt của {current_player.mention if current_player else 'Nhà Cái'}!", color=discord.Color.dark_red())

        def format_hand(h): return " ".join([f"`{r}{s}`" for r, s in h])
        embed.add_field(name=f"Bài Nhà Cái ({score_hand(self.dealer_hand) if show_all_hands else '?'})", value=format_hand(
            self.dealer_hand) if show_all_hands else "`? ?`"*3, inline=False)
        p_info = "\n".join([f"**{p.display_name}** ({score_hand(s['hand']) if show_all_hands else '?'} nút): {format_hand(s['hand']) if show_all_hands else '`? ?`'*3} - **Cược:** `{s['current_bet']:,}`" for p in self.players if (
            s := self.player_states[p.id])['status'] != 'folded'])
        embed.add_field(name="Bàn cược", value=p_info, inline=False)
        embed.set_footer(
            text=f"Mức cược cần theo: {self.current_bet_to_match:,} coin")
        return embed

    async def next_turn(self):
        active_players = [
            p for p in self.players if self.player_states[p.id]["status"] == "playing"]
        if len(active_players) <= 1:
            return True
        for _ in range(len(self.players)):
            self.current_player_index = (
                self.current_player_index + 1) % len(self.players)
            next_p = self.players[self.current_player_index]
            if self.player_states[next_p.id]["status"] == "playing" and self.player_states[next_p.id]["current_bet"] < self.current_bet_to_match:
                return False
        return True

    async def handle_action(self, interaction: discord.Interaction, action: str, amount=0):
        await interaction.response.defer()
        p_state = self.player_states[interaction.user.id]
        if action == "fold":
            p_state["status"] = "folded"
        elif action in ["call", "raise"]:
            to_pay = (self.current_bet_to_match -
                      p_state["current_bet"]) + (amount if action == "raise" else 0)
            user_data = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
            if user_data["coins"] < to_pay:
                return await interaction.followup.send("Không đủ coin.", ephemeral=True)
            await db.update_coins(interaction.user.id, interaction.guild.id, -to_pay)
            p_state["current_bet"] += to_pay
            if action == "raise":
                self.current_bet_to_match = p_state["current_bet"]

        if await self.next_turn():
            for c in self.children:
                c.disabled = True
            await self.message.edit(embed=self.create_game_embed(), view=self)
            await asyncio.sleep(2.5)
            await self.showdown()
        else:
            await self.message.edit(embed=self.create_game_embed(), view=self)

    async def showdown(self):
        self.stop()
        dealer_score = score_hand(self.dealer_hand)
        pot = sum(s['current_bet'] for s in self.player_states.values())
        embed = self.create_game_embed(show_all_hands=True)
        embed.title = "🃏 KẾT QUẢ 🃏"
        embed.description = f"Tổng tiền cược: **{pot:,}** coin"
        winners, best_score = [], -1
        playing_players = [
            p for p in self.players if self.player_states[p.id]["status"] != "folded"]
        if len(playing_players) == 1:
            winners = playing_players
        else:
            for p in playing_players:
                p_score = score_hand(self.player_states[p.id]["hand"])
                if p_score >= dealer_score:
                    if p_score > best_score:
                        best_score, winners = p_score, [p]
                    elif p_score == best_score:
                        winners.append(p)

        result_text = "Nhà cái thắng!" if not winners else "\n".join(
            [f"🎉 {w.mention} thắng **{pot//len(winners):,}** coin!" for w in winners])
        if winners:
            for w in winners:
                await db.update_coins(w.id, w.guild.id, pot // len(winners))

        embed.add_field(name="--- KẾT QUẢ ---",
                        value=result_text, inline=False)
        bet_amount = self.original_ctx.kwargs.get(
            'bet_amount', self.player_states[self.players[0].id]['current_bet'])
        new_lobby_view = CreateNewLobbyView(
            self.cog, self.original_ctx, 'poker', bet_amount)
        await self.message.edit(embed=embed, view=new_lobby_view)

    @discord.ui.button(label="👁️ Xem Bài", style=discord.ButtonStyle.secondary, row=1, custom_id="view_hand_button")
    async def view_hand(self, interaction: discord.Interaction, button: discord.ui.Button):
        p_state = self.player_states.get(interaction.user.id)
        if not p_state or p_state["status"] == "folded":
            return await interaction.response.send_message("Lỗi.", ephemeral=True)
        hand, score = p_state["hand"], score_hand(p_state["hand"])
        await interaction.response.send_message(f"Bài của bạn: {' '.join([f'`{r}{s}`' for r, s in hand])} ({score} nút).", ephemeral=True)

    @discord.ui.button(label="Theo", style=discord.ButtonStyle.green)
    async def call(self, interaction: discord.Interaction,
                   button: discord.ui.Button): await self.handle_action(interaction, "call")

    @discord.ui.button(label="Tố", style=discord.ButtonStyle.primary)
    async def raise_btn(self, interaction: discord.Interaction,
                        button: discord.ui.Button): await interaction.response.send_modal(PokerRaiseModal(self))

    @discord.ui.button(label="Bỏ Bài", style=discord.ButtonStyle.red)
    async def fold(self, interaction: discord.Interaction,
                   button: discord.ui.Button): await self.handle_action(interaction, "fold")


class PokerLobbyView(discord.ui.View):
    def __init__(self, host: discord.Member, bet_amount: int, cog):
        super().__init__(timeout=120.0)
        self.host, self.bet_amount, self.cog = host, bet_amount, cog
        self.players = {host}
        self.message = None
        self.original_ctx = None

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🃏 Bàn Bài 3 Lá - Cược Sàn {self.bet_amount:,} Coin 🃏", description="Nhấn nút **Tham Gia**!", color=0x006400)
        embed.add_field(name=f"Người chơi ({len(self.players)})", value="\n".join(
            [p.mention for p in self.players]) or "Chưa có ai.")
        embed.set_footer(
            text=f"Chủ xị ({self.host.display_name}) có thể bắt đầu.")
        return embed

    @discord.ui.button(label="Tham Gia", emoji="🎟️")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            return await interaction.response.send_message("Bạn đã tham gia.", ephemeral=True)
        user_data = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        if user_data['coins'] < self.bet_amount:
            return await interaction.response.send_message(f"Không đủ **{self.bet_amount:,}** coin.", ephemeral=True)
        self.players.add(interaction.user)
        await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(label="Bắt Đầu", emoji="▶️")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị có thể bắt đầu.", ephemeral=True)
        if len(self.players) < 1:
            return await interaction.response.send_message("Cần ít nhất 1 người.", ephemeral=True)
        await interaction.response.defer()
        self.stop()
        for p in self.players:
            await db.update_coins(p.id, interaction.guild.id, -self.bet_amount)
        game_view = PokerGameView(
            list(self.players), self.bet_amount, self.message, self.cog, self.original_ctx)

        def format_hand(h): return " ".join([f"`{r}{s}`" for r, s in h])
        for p in game_view.players:
            p_state = game_view.player_states[p.id]
            hand, score = p_state["hand"], score_hand(p_state["hand"])
            try:
                await p.send(f"Bài của bạn: {format_hand(hand)} ({score} nút).")
            except:
                pass
        await self.message.edit(embed=game_view.create_game_embed(), view=game_view)

    @discord.ui.button(label="Hủy", emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Chỉ chủ xị có thể hủy.", ephemeral=True)
        embed = self.create_embed()
        embed.title = "[ĐÃ HỦY] " + embed.title
        embed.description = "Bàn cược đã hủy."
        embed.color = discord.Color.dark_grey()
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

# =============================================================
# COG CHÍNH
# =============================================================


class Fun(commands.Cog):
    """🎲 Các lệnh giải trí và mini-game vui vẻ."""
    COG_EMOJI = "🎲"
    def __init__(self, bot): self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        config = await db.get_or_create_config(ctx.guild.id)
        if (debtor_role_id := config.get('debtor_role_id')) and (debtor_role := ctx.guild.get_role(debtor_role_id)) and debtor_role in ctx.author.roles:
            await ctx.send("Bạn đang trong tình trạng vỡ nợ!", ephemeral=True, delete_after=10)
            return False
        return True

    # cogs/fun.py -> class Fun

    @commands.hybrid_command(name="coin", description="Tung đồng xu Sấp/Ngửa, có thể cược coin.")
    @app_commands.rename(bet="tiền_cược")
    async def coin(self, ctx: commands.Context, bet: int = 0):
        if bet > 0:
            user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
            if user_data['coins'] < bet:
                return await ctx.send(f"Bạn không đủ **{bet:,}** coin.", ephemeral=True)

            is_win = random.choice([True, False])
            if is_win:
                await db.update_coins(ctx.author.id, ctx.guild.id, bet)
                embed = discord.Embed(
                    title="🎉 BẠN THẮNG! 🎉", description=f"Bạn thắng **{bet:,}** coin.", color=discord.Color.gold())
            else:
                await db.update_coins(ctx.author.id, ctx.guild.id, -bet)
                embed = discord.Embed(
                    title="💔 BẠN THUA! 💔", description=f"Bạn mất **{bet:,}** coin.", color=discord.Color.dark_grey())

            # <<< SỬA LỖI TẠI ĐÂY: THÊM LẠI SET_AUTHOR >>>
            embed.set_author(
                name=f"Ván cược của {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

            new_balance = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
            embed.set_footer(text=f"Số dư mới: {new_balance['coins']:,} coin")
            view = PlayAgainView(self, ctx, 'coin', 'Cược Lại Tung Đồng Xu')
            await ctx.send(embed=embed, view=view)
        else:
            result = 'Sấp' if random.random() > 0.5 else 'Ngửa'
            embed = discord.Embed(
                title=f"🪙 Kết quả: {result}!", color=discord.Color.blue())

            # <<< THÊM CẢ VÀO ĐÂY ĐỂ ĐỒNG BỘ >>>
            embed.set_author(
                name=f"Lượt tung của {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

            view = CoinNoBetView(self, ctx)
            await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="flip", description="Tạo bàn cược tung đồng xu cho nhiều người.")
    @app_commands.rename(bet_amount="số_tiền_cược")
    async def flip(self, ctx: commands.Context, bet_amount: int):
        if bet_amount <= 0:
            return await ctx.send("Tiền cược phải lớn hơn 0.", ephemeral=True)
        host_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if host_data['coins'] < bet_amount:
            return await ctx.send(f"Bạn không đủ **{bet_amount:,}** coin.", ephemeral=True)
        lobby_view = CoinflipLobbyView(ctx.author, bet_amount, self)
        lobby_view.original_ctx = ctx
        lobby_view.message = await ctx.send(embed=lobby_view.create_embed(), view=lobby_view)

    @commands.hybrid_command(name="roll", description="Tung xúc xắc (mặc định 6 mặt).")
    @app_commands.rename(sides="số_mặt")
    async def roll(self, ctx: commands.Context, sides: int = 6):
        if sides <= 1:
            return await ctx.send("Số mặt phải lớn hơn 1.", ephemeral=True)
        await ctx.send(embed=discord.Embed(description=f"🎲 Bạn đã tung ra số **{random.randint(1, sides)}**.", color=0x992D22))

    @commands.hybrid_command(name="rps", aliases=['rockpaperscissors'], description="Thách đấu Oẳn tù tì.")
    @app_commands.rename(member="đối_thủ", bet_amount="số_tiền_cược")
    async def rockpaperscissors(self, ctx: commands.Context, member: discord.Member, bet_amount: int = 0):
        if member == ctx.author or member.bot:
            return await ctx.send("Không thể thách đấu với chính mình hoặc bot.", ephemeral=True)
        if bet_amount < 0:
            return await ctx.send("Tiền cược không thể âm.", ephemeral=True)
        if bet_amount > 0:
            p1_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
            p2_data = await db.get_or_create_user(member.id, ctx.guild.id)
            if p1_data['coins'] < bet_amount or p2_data['coins'] < bet_amount:
                return await ctx.send("Một trong hai người không đủ tiền cược.", ephemeral=True)

        invite_view = ConfirmationView(member)
        invite_msg = await ctx.send(f"{member.mention}, bạn có chấp nhận lời thách đấu từ {ctx.author.mention}{f' (cược {bet_amount:,} coin)' if bet_amount > 0 else ''}?", view=invite_view)

        await invite_view.wait()

        if invite_view.confirmed:
            await invite_msg.delete()
            game_view = RPSGameView(ctx.author, member)
            await ctx.send(embed=discord.Embed(title="⚔️ Trận Đấu Bắt Đầu! ⚔️", description=f"{ctx.author.mention} vs {member.mention}", color=discord.Color.yellow()), view=game_view)

            await game_view.wait()

            winner, p1c, p2c = game_view.winner, game_view.choices.get(
                ctx.author.id), game_view.choices.get(member.id)

            # Xử lý trường hợp một người không chọn
            if not p1c or not p2c:
                # Nếu game hết hạn mà có người chưa chọn, không cần làm gì thêm, view tự stop
                return

            embed = discord.Embed(title="Kết Quả Oẳn Tù Tì")
            embed.add_field(name=ctx.author.display_name,
                            value=game_view.CHOICE_EMOJIS.get(p1c, "❓"))
            embed.add_field(name=member.display_name,
                            value=game_view.CHOICE_EMOJIS.get(p2c, "❓"))

            if winner == "hòa":
                embed.description = "Hòa nhau!"
            elif winner:
                loser = member if winner == ctx.author else ctx.author
                embed.description = f"**{winner.display_name}** đã chiến thắng! 👑"
                if bet_amount > 0:
                    await db.update_coins(winner.id, ctx.guild.id, bet_amount)
                    await db.update_coins(loser.id, ctx.guild.id, -bet_amount)
                    embed.description += f"\n**{winner.mention}** thắng **{bet_amount:,}** coin!"
                await db.update_quest_progress(winner.id, ctx.guild.id, 'RPS_WIN')

            # =============================================================
            # <<< PHẦN CẬP NHẬT CHÍNH NẰM Ở ĐÂY >>>
            # Tạo view mới với tùy chọn thách đấu lại thay cho view cũ chỉ có nút đóng
            replay_view = RPSReplayView(self, ctx, member, bet_amount)
            await ctx.send(embed=embed, view=replay_view)
            # =============================================================

        elif invite_view.confirmed is False:
            await invite_msg.edit(content=f"{member.display_name} đã từ chối.", view=None, delete_after=10)
        else:  # Timeout
            await invite_msg.edit(content="Lời thách đấu đã hết hạn.", view=None, delete_after=10)

    @commands.hybrid_command(name="duangua", description="Tạo một cuộc đua ngựa để mọi người đặt cược.")
    async def horse_race(self, ctx: commands.Context):
        view = HorseRacingLobbyView(ctx.author, self)
        view.original_ctx = ctx
        view.message = await ctx.send(embed=view.create_lobby_embed(), view=view)

    async def start_the_race(self, view: HorseRacingLobbyView):
        [setattr(i, 'disabled', True) for i in view.children]
        total_pot = sum(b['amount']
                        for bets in view.bets.values() for b in bets)
        for u, bets in view.bets.items():
            await db.update_coins(u.id, view.host.guild.id, -sum(b['amount'] for b in bets))
        race_len = 20
        embed = discord.Embed(title="🏇 CUỘC ĐUA BẮT ĐẦU! 🏇",
                              color=discord.Color.blue())
        bet_info = "\n".join(
            [f"**{u.display_name}:** {', '.join([f'{view.horses[b['horse']]['emoji']} ({b['amount']:,})' for b in bets])}" for u, bets in view.bets.items()])
        if bet_info:
            embed.add_field(name="--- Cược Thủ ---", value=bet_info)
        embed.description = "\n".join(
            [f"`{'🏁' + '-' * race_len}` {h['emoji']}" for h in view.horses])
        await view.message.edit(embed=embed, view=view)
        await asyncio.sleep(2)
        winner = None
        while winner is None:
            desc = ""
            for i, h in enumerate(view.horses):
                h["progress"] = min(
                    race_len, h["progress"] + random.randint(1, 3))
                desc += f"`{'🏁' + '-' * (race_len - h['progress']) + h['emoji'] + '-' * h['progress']}`\n"
                if h["progress"] >= race_len and winner is None:
                    winner = i
            embed.description = desc
            await view.message.edit(embed=embed)
            if winner is not None:
                break
            await asyncio.sleep(2)
        winner_horse = view.horses[winner]
        embed.title = f"🏁 KẾT THÚC! {winner_horse['emoji']} CHIẾN THẮNG! 🏁"
        winning_bets = [{"user": u, "amount": b["amount"]}
                        for u, bets in view.bets.items() for b in bets if b["horse"] == winner]
        result_text = f"Không ai cược cho {winner_horse['emoji']}. Nhà cái hưởng **{total_pot:,}** coin!"
        if winning_bets:
            payout_per_coin = total_pot / \
                sum(b["amount"] for b in winning_bets) if sum(b["amount"]
                                                              for b in winning_bets) > 0 else 0
            payouts = {}
            for bet in winning_bets:
                payouts[bet["user"]] = payouts.get(
                    bet["user"], 0) + int(bet["amount"] * payout_per_coin)
            for u, p in payouts.items():
                await db.update_coins(u.id, view.host.guild.id, p)
            result_text = "\n".join(
                [f"{u.mention} thắng **{p:,}** coin!" for u, p in payouts.items()])
        embed.add_field(name="--- KẾT QUẢ ---",
                        value=result_text, inline=False)
        new_lobby_view = CreateNewLobbyView(self, view.original_ctx, 'duangua')
        await view.message.edit(embed=embed, view=new_lobby_view)

    @commands.hybrid_command(name="taixiu", aliases=['tx'], description="Tạo bàn cược Tài Xỉu.")
    @app_commands.rename(bet_amount="số_tiền_cược")
    async def tai_xiu_table(self, ctx: commands.Context, bet_amount: int):
        if bet_amount <= 0:
            return await ctx.send("Tiền cược phải lớn hơn 0.", ephemeral=True)
        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if user_data['coins'] < bet_amount:
            return await ctx.send(f"Không đủ **{bet_amount:,}** coin.", ephemeral=True)
        view = TaixiuLobbyView(ctx.author, bet_amount, self)
        view.original_ctx = ctx
        view.message = await ctx.send(embed=view.create_embed(), view=view)

    @commands.hybrid_command(name="poker", aliases=['xito'], description="Tạo bàn chơi Poker 3 lá.")
    @app_commands.rename(bet_amount="số_tiền_cược")
    async def poker_table(self, ctx: commands.Context, bet_amount: int):
        if bet_amount <= 0:
            return await ctx.send("Tiền cược phải lớn hơn 0.", ephemeral=True)
        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if user_data['coins'] < bet_amount:
            return await ctx.send(f"Không đủ **{bet_amount:,}** coin.", ephemeral=True)
        view = PokerLobbyView(ctx.author, bet_amount, self)
        view.original_ctx = ctx
        view.message = await ctx.send(embed=view.create_embed(), view=view)

    @commands.hybrid_command(name="slots", aliases=['sl'], description="Chơi máy kéo may mắn.")
    @app_commands.rename(bet="tiền_cược")
    async def slots(self, ctx: commands.Context, bet: int):
        if bet <= 0:
            return await ctx.send("Tiền cược phải lớn hơn 0.", ephemeral=True)
        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if user_data['coins'] < bet:
            return await ctx.send(f"Bạn không đủ **{bet:,}** coin.", ephemeral=True)
        await db.update_coins(ctx.author.id, ctx.guild.id, -bet)
        reels = {"🍒": 40, "🍊": 30, "🍓": 20, "💰": 10, "💎": 5, "7️⃣": 2}
        results = random.choices(
            list(reels.keys()), weights=list(reels.values()), k=3)
        slot_msg = await ctx.send(f"**[ ❓ | ❓ | ❓ ]**\nĐang quay...")
        for i in range(3):
            await asyncio.sleep(1)
            content = f"**[ {' | '.join(results[:i+1])}{' | ❓ ' * (2-i)}]**".strip()
            await slot_msg.edit(content=content)
        payout, win_msg, title, color = 0, "", "💔 BẠN THUA! 💔", discord.Color.dark_grey()
        if results[0] == results[1] == results[2]:
            title, color = "🎉 BẠN THẮNG! 🎉", discord.Color.gold()
            payout = bet * {'7️⃣': 100, '💎': 50, '💰': 20,
                            '🍓': 10, '🍊': 5, '🍒': 3}.get(results[0], 0)
            win_msg = "🎉 JACKPOT! 🎉" if results[0] == "7️⃣" else "Thắng lớn!"
        elif results.count("🍒") == 2:
            title, color = "🎉 BẠN THẮNG! 🎉", discord.Color.gold()
            payout, win_msg = int(bet * 1.5), "Hai quả cherry!"
        embed = discord.Embed(
            title=title, color=color, description=f"**[ {results[0]} | {results[1]} | {results[2]} ]**\n*{win_msg}*")
        embed.add_field(name="Tiền cược", value=f"`{bet:,}` coin", inline=True)
        if payout > 0:
            await db.update_coins(ctx.author.id, ctx.guild.id, payout)
            embed.add_field(name="Tiền thắng",
                            value=f"`{payout:,}` coin", inline=True)
        else:
            embed.add_field(name="Tiền thua",
                            value=f"`{bet:,}` coin", inline=True)
        new_balance = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        embed.add_field(
            name="Số dư mới", value=f"**{new_balance['coins']:,}** coin", inline=False)
        embed.set_author(
            name=f"Ván cược của {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        view = PlayAgainView(self, ctx, 'slots', 'Cược Lại Slots')
        await slot_msg.edit(content=None, embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Fun(bot))
