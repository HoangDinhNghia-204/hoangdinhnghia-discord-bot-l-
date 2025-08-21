# cogs/economy.py
import discord
from discord.ext import commands
import random
import datetime
from typing import Union
import re
import database as db
from .utils import checks
from discord import app_commands

# --- HÀM HELPER ---


def parse_duration(duration_str: str) -> datetime.timedelta:
    if duration_str == "0":
        return datetime.timedelta(seconds=0)
    match = re.match(r"(\d+)([mhd])", duration_str.lower())
    if not match:
        raise ValueError(
            "Định dạng thời gian không hợp lệ. Dùng 'm', 'h', 'd'.")
    value, unit = int(match.group(1)), match.group(2)
    if unit == 'm':
        return datetime.timedelta(minutes=value)
    if unit == 'h':
        return datetime.timedelta(hours=value)
    if unit == 'd':
        return datetime.timedelta(days=value)


def format_duration(total_seconds: int) -> str:
    if total_seconds == 0:
        return "Vĩnh viễn"
    parts = []
    days, rem = divmod(total_seconds, 86400)
    if days > 0:
        parts.append(f"{days} ngày")
    hours, rem = divmod(rem, 3600)
    if hours > 0:
        parts.append(f"{hours} giờ")
    minutes, _ = divmod(rem, 60)
    if minutes > 0:
        parts.append(f"{minutes} phút")
    return " ".join(parts) if parts else "Ngay lập tức"


SHOP_ITEMS = {
    "xp_booster": {"name": "Bùa Tăng XP (24h)", "price": 10000, "description": "Tăng 50% XP nhận được trong 24 giờ.", "emoji": "✨", "usable": True},
    "lottery_ticket": {"name": "Vé Xổ Số", "price": 100, "description": "Cơ hội trúng giải độc đắc!", "emoji": "🎟️", "usable": False},
    "coin_booster_3h": {"name": "Bùa Tăng Coin (3h)", "price": 7500, "description": "Tăng 25% coin nhận được từ tin nhắn trong 3 giờ.", "emoji": "💰", "usable": True},
    "nickname_ticket": {"name": "Thẻ Đổi Tên", "price": 30000, "description": "Vào kho đồ để dùng.", "emoji": "🎫", "usable": True}
}


class NicknameModal(discord.ui.Modal, title="Đổi Nickname"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
    new_name_input = discord.ui.TextInput(
        label="Nhập nickname mới của bạn", placeholder="Ví dụ: Quần Sịp Bảy Màu", required=True, max_length=32)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.new_name_input.value
        try:
            old_name = interaction.user.display_name
            await interaction.user.edit(nick=new_name, reason="Sử dụng Thẻ Đổi Tên từ shop")
            await db.remove_item_from_inventory(interaction.user.id, interaction.guild.id, 'nickname_ticket', 1)
            await interaction.response.send_message(f"✅ Đã đổi tên thành công từ `{old_name}` thành `{new_name}`!", ephemeral=True)
            if interaction.message:
                new_embed = await self.cog.create_inventory_embed(interaction.user)
                new_view = await InventoryView.create(interaction.user, self.cog)
                await interaction.message.edit(embed=new_embed, view=new_view)
        except discord.Forbidden:
            await interaction.response.send_message("⚠️ Lỗi: Bot không có quyền để đổi tên cho bạn. Vui lòng liên hệ Admin.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Đã có lỗi xảy ra: {e}", ephemeral=True)


class InventoryView(discord.ui.View):
    def __init__(self, author: discord.Member, cog):
        super().__init__(timeout=180.0)
        self.author = author
        self.cog = cog

    @classmethod
    async def create(cls, author: discord.Member, cog):
        view = cls(author, cog)
        await view.update_select_options()
        return view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Đây không phải kho đồ của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Chọn một vật phẩm để sử dụng...")
    async def use_item_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        item_id = select.values[0]
        if item_id == "placeholder_none":
            return await interaction.response.defer()
        if item_id == "nickname_ticket":
            if not await db.check_inventory_item(self.author.id, self.author.guild.id, 'nickname_ticket'):
                await interaction.response.send_message("Lỗi: Bạn không có vật phẩm này trong kho.", ephemeral=True)
                await self.update_select_options()
                await interaction.message.edit(view=self)
                return
            await interaction.response.send_modal(NicknameModal(self.cog))
            return

        await interaction.response.defer()

        if item_id == "xp_booster":
            if await db.get_user_active_effect(self.author.id, self.author.guild.id, 'xp_booster'):
                return await interaction.followup.send("Bạn đã có một Bùa Tăng XP đang hoạt động rồi.", ephemeral=True)
            if await db.remove_item_from_inventory(self.author.id, self.author.guild.id, item_id, 1):
                expiry = datetime.datetime.now(
                    datetime.timezone.utc) + datetime.timedelta(hours=24)
                await db.add_active_effect(self.author.id, self.author.guild.id, 'xp_booster', expiry.isoformat())
                await interaction.followup.send(f"✨ Bạn đã kích hoạt **Bùa Tăng XP**!", ephemeral=True)
            else:
                await interaction.followup.send("Lỗi: Bạn không có vật phẩm này trong kho.", ephemeral=True)

        elif item_id == "coin_booster_3h":
            if await db.get_user_active_effect(self.author.id, self.author.guild.id, 'coin_booster'):
                return await interaction.followup.send("Bạn đã có một Bùa Tăng Coin đang hoạt động rồi.", ephemeral=True)
            if await db.remove_item_from_inventory(self.author.id, self.author.guild.id, item_id, 1):
                expiry = datetime.datetime.now(
                    datetime.timezone.utc) + datetime.timedelta(hours=3)
                await db.add_active_effect(self.author.id, self.author.guild.id, 'coin_booster', expiry.isoformat())
                await interaction.followup.send(f"💰 Bạn đã kích hoạt **Bùa Tăng Coin**!", ephemeral=True)
            else:
                await interaction.followup.send("Lỗi: Bạn không có vật phẩm này trong kho.", ephemeral=True)
        else:
            await interaction.followup.send(f"Vật phẩm `{item_id}` chưa có chức năng sử dụng.", ephemeral=True)
            return

        new_embed = await self.cog.create_inventory_embed(self.author)
        await self.update_select_options()
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Đóng", style=discord.ButtonStyle.red, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

    async def update_select_options(self):
        user_inventory = await db.get_user_inventory(self.author.id, self.author.guild.id)
        options = [discord.SelectOption(label=item_data["name"], value=item_id, emoji=item_data["emoji"], description=f"Số lượng: x{quantity}") for item_id, quantity in user_inventory.items(
        ) if (item_data := SHOP_ITEMS.get(item_id)) and item_data.get("usable")]
        select_menu = self.children[0]
        if not options:
            select_menu.options = [discord.SelectOption(
                label="Không có vật phẩm nào để dùng", value="placeholder_none", emoji="🤷")]
            select_menu.disabled = True
        else:
            select_menu.options = options
            select_menu.disabled = False


class ShopView(discord.ui.View):
    def __init__(self, author: discord.Member, all_items: list, cog):
        super().__init__(timeout=180.0)
        self.author = author
        self.all_items = all_items
        self.cog = cog
        self.current_page = 0

    @classmethod
    async def create(cls, author: discord.Member, all_items: list, cog):
        view = cls(author, all_items, cog)
        await view.update_components()
        return view

    async def create_embed(self) -> discord.Embed:
        item = self.all_items[self.current_page]
        user_data = await db.get_or_create_user(self.author.id, self.author.guild.id)
        embed = discord.Embed(color=discord.Color.teal())
        embed.set_author(
            name=f"Cửa Hàng Dành Cho {self.author.display_name}", icon_url=self.author.display_avatar.url)
        if 'role_id' in item:
            role = self.author.guild.get_role(item['role_id'])
            if not role:
                embed.description = "Lỗi: Role này không còn tồn tại."
                return embed
            embed.title, embed.color = f"✨ Vai Trò: {role.name}", role.color
            embed.description = f"*{item['description'] or 'Chưa có mô tả cho vai trò này.'}*"
            embed.add_field(
                name="Giá Bán", value=f"**{item['price']:,}** coin", inline=True)
            embed.add_field(
                name="Thời Hạn", value=f"{format_duration(item['duration_seconds'])}", inline=True)
        else:
            embed.title = f"{item['emoji']} Vật Phẩm: {item['name']}"
            embed.description = f"*{item['description'] or 'Chưa có mô tả cho vật phẩm này.'}*"
            embed.add_field(
                name="Giá Bán", value=f"**{item['price']:,}** coin", inline=True)
            embed.add_field(name="Mã Vật Phẩm",
                            value=f"`{item['id']}`", inline=True)
        embed.add_field(name="\u200b", value="-"*40, inline=False)
        embed.add_field(name="Số Dư Của Bạn",
                        value=f"💰 **{user_data['coins']:,}** coin", inline=True)
        embed.set_footer(
            text=f"Trang {self.current_page + 1}/{len(self.all_items)}")
        return embed

    async def update_components(self):
        if not self.all_items:
            for child in self.children:
                child.disabled = True
            return
        current_item = self.all_items[self.current_page]
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page == len(
            self.all_items) - 1
        self.children[2].label = f"Mua ({current_item['price']:,} coin)"
        if 'role_id' in current_item:
            role = self.author.guild.get_role(current_item['role_id'])
            self.children[2].disabled = not role or role in self.author.roles
        else:
            self.children[2].disabled = False

    async def show_current_page(self, interaction: discord.Interaction):
        await self.update_components()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⬅️ Trước", style=discord.ButtonStyle.secondary, row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Đây không phải cửa hàng của bạn!", ephemeral=True)
        self.current_page -= 1
        await self.show_current_page(interaction)

    @discord.ui.button(label="Sau ➡️", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Đây không phải cửa hàng của bạn!", ephemeral=True)
        self.current_page += 1
        await self.show_current_page(interaction)

    @discord.ui.button(emoji="🛍️", style=discord.ButtonStyle.green, row=1)
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Đây không phải cửa hàng của bạn!", ephemeral=True)
        item_to_buy = self.all_items[self.current_page]
        user_data = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        price = item_to_buy['price']
        if user_data['coins'] < price:
            return await interaction.response.send_message(f"Bạn không đủ coin.", ephemeral=True)
        await db.update_coins(interaction.user.id, interaction.guild.id, -price)
        await self.cog.update_shop_achievements(interaction, price)
        if 'role_id' in item_to_buy:
            role = interaction.guild.get_role(item_to_buy['role_id'])
            await interaction.user.add_roles(role, reason="Mua từ shop")
            duration_seconds = item_to_buy['duration_seconds']
            if duration_seconds > 0:
                expiry = datetime.datetime.now(
                    datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
                await db.add_temporary_role(interaction.user.id, interaction.guild.id, role.id, expiry.isoformat())
            await interaction.response.send_message(f"Bạn đã mua thành công role {role.mention}!", ephemeral=True)
        else:
            item_id = item_to_buy['id']
            await db.add_item_to_inventory(interaction.user.id, interaction.guild.id, item_id, 1)
            if item_id == 'lottery_ticket':
                await db.add_lottery_tickets(interaction.guild.id, interaction.user.id, 1)
                await interaction.response.send_message(f"Bạn đã mua thành công 1 vé xổ số!", ephemeral=True)
            else:
                await interaction.response.send_message(f"Bạn đã mua thành công **{item_to_buy['name']}** và đã được cất vào kho đồ.", ephemeral=True)
        await self.show_current_page(interaction)

    @discord.ui.button(label="Đóng", style=discord.ButtonStyle.red, row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("Đây không phải cửa hàng của bạn!", ephemeral=True)
        await interaction.message.delete()


class Economy(commands.Cog):
    """💰 Hệ thống kinh tế, shop, và các mini-game."""
    COG_EMOJI = "💰"

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context):
        if ctx.command.name == 'balance':
            return True
        config = await db.get_or_create_config(ctx.guild.id)
        if debtor_role_id := config.get('debtor_role_id'):
            if debtor_role := ctx.guild.get_role(debtor_role_id):
                if debtor_role in ctx.author.roles:
                    await ctx.send("Bạn đang trong tình trạng vỡ nợ và không thể sử dụng lệnh này! Dùng `/trano` để trả nợ.", ephemeral=True, delete_after=10)
                    return False
        return True

    async def update_shop_achievements(self, source: Union[commands.Context, discord.Interaction], price: int):
        user = source.author if isinstance(
            source, commands.Context) else source.user
        guild = source.guild
        await db.update_quest_progress(user.id, guild.id, 'SHOP_BUY')
        await db.update_quest_progress(user.id, guild.id, 'COIN_SPEND', value_to_add=price)
        unlocked_buy = await db.update_achievement_progress(user.id, guild.id, 'SHOP_BUY')
        if unlocked_buy:
            for ach in unlocked_buy:
                await source.channel.send(f"🏆 {user.mention} vừa mở khóa thành tựu mới: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)
        unlocked_spend = await db.update_achievement_progress(user.id, guild.id, 'COIN_SPEND', value_to_add=price)
        if unlocked_spend:
            for ach in unlocked_spend:
                await source.channel.send(f"🏆 {user.mention} vừa mở khóa thành tựu mới: **{ach['name']}**! (+{ach['reward_coin']:,} coin, +{ach['reward_xp']} XP)", delete_after=30)

    async def create_inventory_embed(self, member: discord.Member) -> discord.Embed:
        inv_items = await db.get_user_inventory(member.id, member.guild.id)
        embed = discord.Embed(
            title=f"🎒 Kho đồ của {member.display_name}", color=member.color)
        item_parts = [f"{item['emoji']} **{item['name']}**: `x{quantity}`" for item_id,
                      quantity in inv_items.items() if (item := SHOP_ITEMS.get(item_id))]
        if item_parts:
            embed.add_field(name="Vật phẩm trong kho",
                            value="\n".join(item_parts), inline=False)
        effect_parts = []
        if booster := await db.get_user_active_effect(member.id, member.guild.id, 'xp_booster'):
            expiry_ts = int(datetime.datetime.fromisoformat(
                booster['expiry_timestamp']).timestamp())
            effect_parts.append(
                f"✨ **Bùa Tăng XP**: Hết hạn <t:{expiry_ts}:R>")
        if booster_coin := await db.get_user_active_effect(member.id, member.guild.id, 'coin_booster'):
            expiry_ts = int(datetime.datetime.fromisoformat(
                booster_coin['expiry_timestamp']).timestamp())
            effect_parts.append(
                f"💰 **Bùa Tăng Coin**: Hết hạn <t:{expiry_ts}:R>")
        if effect_parts:
            embed.add_field(name="⚡ Hiệu ứng đang hoạt động",
                            value="\n".join(effect_parts), inline=False)
        if not item_parts and not effect_parts:
            embed.description = "Kho đồ của bạn trống trơn."
        return embed

    @commands.hybrid_command(name="inventory", aliases=['inv'], description="Xem kho đồ và sử dụng vật phẩm.")
    @app_commands.rename(member="tên")
    async def inventory(self, ctx: commands.Context, member: discord.Member = None):
        target_member = member or ctx.author
        embed = await self.create_inventory_embed(target_member)
        if target_member == ctx.author:
            view = await InventoryView.create(ctx.author, self)
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="shop", description="Mở cửa hàng tương tác để mua vật phẩm và role.")
    async def shop(self, ctx: commands.Context):
        all_items = [{'id': item_id, **data}
                     for item_id, data in SHOP_ITEMS.items()]
        shop_roles = await db.get_shop_roles(ctx.guild.id)
        all_items.extend(shop_roles)
        if not all_items:
            return await ctx.send("Cửa hàng hiện đang trống.", ephemeral=True)
        view = await ShopView.create(ctx.author, all_items, self)
        initial_embed = await view.create_embed()
        await ctx.send(embed=initial_embed, view=view)

    @commands.hybrid_command(name="buy", description="Mua nhanh một vật phẩm hoặc role từ shop.")
    @app_commands.rename(item_or_role_name="tên_vật_phẩm_hoặc_role")
    async def buy(self, ctx: commands.Context, *, item_or_role_name: str):
        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        item_to_buy, price, is_role, item_id, item_or_role_obj = None, 0, False, None, None

        try:
            role_converter = commands.RoleConverter()
            item_or_role_obj = await role_converter.convert(ctx, item_or_role_name)
            is_role = True
        except commands.RoleNotFound:
            is_role = False

        if is_role:
            shop_role = await db.get_shop_role(ctx.guild.id, item_or_role_obj.id)
            if not shop_role:
                return await ctx.send("Role này không bán trong shop.", delete_after=10, ephemeral=True)
            if item_or_role_obj in ctx.author.roles:
                return await ctx.send("Bạn đã có role này.", delete_after=10, ephemeral=True)
            item_to_buy, price = shop_role, shop_role['price']
        else:
            item_name_str = item_or_role_name
            for i_id, i_data in SHOP_ITEMS.items():
                if i_data['name'].lower() == item_name_str.lower():
                    item_id = i_id
                    item_to_buy = i_data
                    price = i_data['price']
                    break

            if not item_to_buy:
                return await ctx.send(f"Không tìm thấy vật phẩm hoặc role có tên `{item_name_str}`.", delete_after=10, ephemeral=True)

        if user_data['coins'] < price:
            return await ctx.send(f"Bạn không đủ **{price:,}** coin để mua.", delete_after=10, ephemeral=True)

        await db.update_coins(ctx.author.id, ctx.guild.id, -price)
        await self.update_shop_achievements(ctx, price)

        if is_role:
            await ctx.author.add_roles(item_or_role_obj, reason="Mua từ shop")
            duration_seconds = item_to_buy['duration_seconds']
            if duration_seconds > 0:
                expiry = datetime.datetime.now(
                    datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
                await db.add_temporary_role(ctx.author.id, ctx.guild.id, item_or_role_obj.id, expiry.isoformat())
            await ctx.send(f"🛍️ {ctx.author.mention} đã mua thành công role {item_or_role_obj.mention} (Thời hạn: **{format_duration(duration_seconds)}**).")
        else:
            await db.add_item_to_inventory(ctx.author.id, ctx.guild.id, item_id, 1)
            if item_id == 'lottery_ticket':
                await db.add_lottery_tickets(ctx.guild.id, ctx.author.id, 1)
                await ctx.send(f"✅ Bạn đã mua thành công 1 vé xổ số!")
            else:
                await ctx.send(f"🛍️ Bạn đã mua **{item_to_buy['name']}** và cất vào kho đồ (`/inventory`).")

    @commands.hybrid_group(name="shopadmin", description="Các lệnh quản lý cửa hàng (Admin).", hidden=True)
    async def shopadmin(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @shopadmin.command(name="addrole", description="Thêm hoặc cập nhật một role trong shop.")
    @checks.has_permissions(manage_guild=True)
    @app_commands.rename(role="role", price="giá_tiền", duration_str="thời_hạn", description="mô_tả")
    async def shopadmin_addrole(self, ctx: commands.Context, role: discord.Role, price: int, duration_str: str, *, description: str = None):
        if price < 0:
            return await ctx.send("Giá không thể âm.", delete_after=10, ephemeral=True)
        if ctx.guild.me.top_role <= role:
            return await ctx.send(f"Bot không thể quản lý role `{role.name}`.", delete_after=15, ephemeral=True)
        try:
            duration_seconds = int(parse_duration(
                duration_str).total_seconds())
        except ValueError as e:
            return await ctx.send(f"❌ {e}", delete_after=15, ephemeral=True)
        if description is None:
            if existing_role := await db.get_shop_role(ctx.guild.id, role.id):
                description = existing_role.get('description')
        await db.add_shop_role(ctx.guild.id, role.id, price, duration_seconds, description)
        message = f"✅ Đã thêm/cập nhật {role.mention} vào shop:\n> **Giá:** {price:,} coin\n> **Thời hạn:** {format_duration(duration_seconds)}"
        if description:
            message += f"\n> **Mô tả:** {description}"
        await ctx.send(message)

    @shopadmin.command(name="removerole", description="Xóa một role khỏi shop.")
    @checks.has_permissions(manage_guild=True)
    async def shopadmin_removerole(self, ctx: commands.Context, role: discord.Role):
        if await db.remove_shop_role(ctx.guild.id, role.id) > 0:
            await ctx.send(f"✅ Đã xóa {role.mention} khỏi shop.")
        else:
            await ctx.send("❌ Role này không có trong shop.", ephemeral=True)

    @commands.hybrid_command(name="balance", aliases=['bal', 'wallet'], description="Xem số dư coin của bạn hoặc người khác.")
    @app_commands.rename(member="tên")
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        target_member = member or ctx.author
        user_data = await db.get_or_create_user(target_member.id, ctx.guild.id)
        embed = discord.Embed(title=f"Ví của {target_member.display_name}",
                              description=f"💰 Số dư: **{user_data['coins']:,}** coin", color=target_member.color)
        embed.set_thumbnail(url=target_member.display_avatar.url)
        await ctx.send(embed=embed)
        if target_member == ctx.author:
            await db.update_quest_progress(ctx.author.id, ctx.guild.id, 'CHECK_BALANCE')

    @commands.hybrid_command(name="daily", description="Nhận thưởng coin hàng ngày của bạn.")
    async def daily(self, ctx: commands.Context):
        user_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        last_daily_str, cooldown = user_data.get(
            'daily_timestamp'), datetime.timedelta(hours=23, minutes=55)
        if last_daily_str:
            last_daily = datetime.datetime.fromisoformat(last_daily_str)
            if (datetime.datetime.now(datetime.timezone.utc) - last_daily) < cooldown:
                remaining = cooldown - \
                    (datetime.datetime.now(datetime.timezone.utc) - last_daily)
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m, _ = divmod(rem, 60)
                return await ctx.send(f"❌ Bạn đã nhận thưởng rồi, quay lại sau **{h} giờ {m} phút**.", delete_after=10, ephemeral=True)
        config, author_roles = await db.get_or_create_config(ctx.guild.id), ctx.author.roles
        luck_role, vip_role = ctx.guild.get_role(config.get(
            'luck_role_id', 0)), ctx.guild.get_role(config.get('vip_role_id', 0))
        min_r, max_r, footer_text = (
            500, 1500, "Hãy quay lại vào ngày mai nhé!")
        if luck_role and luck_role in author_roles:
            min_r, max_r, footer_text = (
                700, 1800, "Thiên Mệnh hộ thể, vận may gia tăng!")
        elif vip_role and vip_role in author_roles:
            min_r, max_r, footer_text = (
                600, 1600, "Đặc quyền VIP, nhận thêm tài lộc!")
        amount = random.randint(min_r, max_r)
        await db.update_coins(ctx.author.id, ctx.guild.id, amount)
        await db.update_daily_timestamp(ctx.author.id, ctx.guild.id, datetime.datetime.now(datetime.timezone.utc).isoformat())
        await db.update_quest_progress(ctx.author.id, ctx.guild.id, 'DAILY_COMMAND')
        embed = discord.Embed(title="🎁 Quà Điểm Danh Hàng Ngày 🎁",
                              description=f"Chúc mừng {ctx.author.mention}, bạn nhận được **{amount:,}** coin!", color=discord.Color.gold())
        embed.set_footer(text=footer_text)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="give", description="Chuyển coin cho một thành viên khác.")
    @app_commands.rename(member="người_nhận", amount="số_tiền")
    async def give(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.send("Số tiền phải lớn hơn 0.", delete_after=10, ephemeral=True)
        if member == ctx.author or member.bot:
            return await ctx.send("Không thể tự chuyển cho mình hoặc bot.", delete_after=10, ephemeral=True)
        author_data = await db.get_or_create_user(ctx.author.id, ctx.guild.id)
        if author_data['coins'] < amount:
            return await ctx.send(f"Không đủ **{amount:,}** coin.", delete_after=10, ephemeral=True)
        await db.update_coins(ctx.author.id, ctx.guild.id, -amount)
        await db.update_coins(member.id, ctx.guild.id, amount)
        await db.update_quest_progress(ctx.author.id, ctx.guild.id, 'GIVE_COIN', value_to_add=amount)
        embed = discord.Embed(
            title="💸 Giao Dịch Chuyển Tiền Thành Công 💸",
            description=f"**{ctx.author.mention}** đã chuyển **{amount:,} coin** cho **{member.mention}**.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Người gửi", value=f"`{ctx.author.display_name}`", inline=True)
        embed.add_field(name="Người nhận", value=f"`{member.display_name}`", inline=True)
        embed.set_footer(text=f"ID Giao dịch: {ctx.interaction.id if ctx.interaction else ctx.message.id}")
        
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="lottery", description="Các lệnh liên quan đến mini-game xổ số.")
    async def lottery(self, ctx: commands.Context):
        pot = await db.get_lottery_pot(ctx.guild.id)
        embed = discord.Embed(title="🎟️ Xổ Số May Mắn 🎟️",
                              description="Thử vận may của bạn!", color=discord.Color.gold())
        embed.add_field(name="💰 Giải thưởng", value=f"**{pot:,}** coin")
        embed.add_field(
            name="📝 Cách chơi", value=f"`/buy item_or_role_name:Vé Xổ Số` để mua.", inline=False)
        await ctx.send(embed=embed)

    # cogs/economy.py

    @lottery.command(name="draw", description="Quay số và tìm ra người thắng cuộc (Admin).")
    @checks.has_permissions(manage_guild=True)
    async def lottery_draw(self, ctx: commands.Context):
        participants = await db.get_lottery_participants(ctx.guild.id)
        pot = await db.get_lottery_pot(ctx.guild.id)

        if not participants:
            return await ctx.send("Chưa có ai tham gia xổ số. Giải thưởng được giữ lại cho lần sau.", ephemeral=True)

        weighted_list = [uid for uid,
                         tickets in participants for _ in range(tickets)]
        if not weighted_list:
            return await ctx.send("Không có vé hợp lệ nào để quay. Giải thưởng được giữ lại cho lần sau.", ephemeral=True)

        winner_id = random.choice(weighted_list)
        try:
            winner = self.bot.get_user(winner_id) or await self.bot.fetch_user(winner_id)
        except discord.NotFound:
            return await ctx.send(f"⚠️ Người thắng cuộc (ID: `{winner_id}`) không còn tồn tại! Giải thưởng **{pot:,}** coin sẽ được bảo toàn.", ephemeral=True)

        # Cập nhật tiền và dọn dẹp database
        await db.update_coins(winner_id, ctx.guild.id, pot)
        await db.clear_lottery(ctx.guild.id)
        await db.remove_item_from_all_inventories(ctx.guild.id, 'lottery_ticket')

        # --- PHẦN NÂNG CẤP THÔNG BÁO MỚI ---

        # 1. Tạo embed thông báo hoành tráng
        embed = discord.Embed(
            title="🏆 KẾT QUẢ XỔ SỐ ĐỘC ĐẮC 🏆",
            description="*Sau những giây phút chờ đợi, vòng quay may mắn đã dừng lại và tìm ra được chủ nhân của giải thưởng khổng lồ!*",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        embed.add_field(
            name="✨ NGƯỜI THẮNG CUỘC ✨",
            value=f"### {winner.mention}\n*({winner})*",  # Tên to, tag nhỏ
            inline=False
        )
        embed.add_field(
            name="💰 GIÁ TRỊ GIẢI THƯỞNG 💰",
            value=f"### {pot:,} coin",
            inline=False
        )
        embed.add_field(
            name="▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
            value="**🎟️ Vòng xổ số mới đã bắt đầu!**\nDùng lệnh `/buy Vé Xổ Số` để thử vận may của bạn!",
            inline=False
        )

        if winner.display_avatar:
            embed.set_thumbnail(url=winner.display_avatar.url)

        embed.set_footer(
            text=f"Quay số bởi: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

        # 2. Lấy kênh thông báo từ config
        config = await db.get_or_create_config(ctx.guild.id)
        announcement_channel_id = config.get('announcement_channel_id')
        target_channel = self.bot.get_channel(
            announcement_channel_id) if announcement_channel_id else None

        # 3. Gửi thông báo
        if target_channel:
            try:
                await target_channel.send(embed=embed)
                await ctx.send(f"✅ Đã quay số thành công. Thông báo chiến thắng đã được gửi đến {target_channel.mention}.", ephemeral=True)
            except discord.Forbidden:
                await ctx.send(embed=embed)
                await ctx.send(f"⚠️ Bot không có quyền gửi tin nhắn trong kênh {target_channel.mention}. Đã gửi thông báo tại đây.", ephemeral=True)
        else:
            await ctx.send(embed=embed)
            await ctx.send("ℹ️ Gợi ý: Dùng lệnh `/set announcement` để đặt kênh thông báo riêng cho các sự kiện như thế này.", ephemeral=True, delete_after=15)


async def setup(bot):
    await bot.add_cog(Economy(bot))
