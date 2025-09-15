# database.py
import aiosqlite
import sqlite3  # Vẫn giữ lại để dùng cho các hàm khởi tạo đồng bộ
import datetime
import json
import random

DB_NAME = 'bot_data.db'


def run_migrations(cursor):
    """Kiểm tra và nâng cấp cấu trúc DB một cách an toàn."""
    print("Bắt đầu kiểm tra và di trú cơ sở dữ liệu...")

    # --- Bảng 'users' ---
    user_columns = [info[1] for info in cursor.execute(
        "PRAGMA table_info(users)").fetchall()]
    if 'coins' not in user_columns:
        print(" > Migration: Đang thêm cột 'coins' vào bảng users...")
        cursor.execute(
            "ALTER TABLE users ADD COLUMN coins INTEGER DEFAULT 0 NOT NULL")
    if 'daily_timestamp' not in user_columns:
        print(" > Migration: Đang thêm cột 'daily_timestamp' vào bảng users...")
        cursor.execute("ALTER TABLE users ADD COLUMN daily_timestamp TEXT")
    if 'perm_damage_bonus' not in user_columns:
        print(" > Migration: Đang thêm cột 'perm_damage_bonus' vào bảng users...")
        cursor.execute(
            "ALTER TABLE users ADD COLUMN perm_damage_bonus REAL DEFAULT 0.0 NOT NULL")

    # --- Bảng 'shop_roles' ---
    try:
        shop_roles_cols_info = cursor.execute(
            "PRAGMA table_info(shop_roles)").fetchall()
        if shop_roles_cols_info:
            shop_roles_cols = [info[1] for info in shop_roles_cols_info]
            if 'description' not in shop_roles_cols:
                print(" > Migration: Đang thêm cột 'description' vào bảng shop_roles...")
                cursor.execute(
                    "ALTER TABLE shop_roles ADD COLUMN description TEXT")
                print("   ✅ Migration description cho 'shop_roles' hoàn tất!")
    except sqlite3.OperationalError:
        pass

    # --- Bảng 'server_configs' ---
    config_columns = [info[1] for info in cursor.execute(
        "PRAGMA table_info(server_configs)").fetchall()]
    cols_to_add = {
        'muted_role_id': 'INTEGER', 'luck_role_id': 'INTEGER', 'top_role_id': 'INTEGER',
        'vip_role_id': 'INTEGER', 'debtor_role_id': 'INTEGER', 'rainbow_role_id': 'INTEGER',
        'create_vc_channel_id': 'INTEGER', 'log_channel_id': 'INTEGER', 'main_chat_channel_id': 'INTEGER',
        'member_count_channel_id': 'INTEGER', 'user_count_channel_id': 'INTEGER', 'bot_count_channel_id': 'INTEGER'
    }
    for col, col_type in cols_to_add.items():
        if col not in config_columns:
            print(
                f" > Migration: Đang thêm cột '{col}' vào bảng server_configs...")
            cursor.execute(
                f"ALTER TABLE server_configs ADD COLUMN {col} {col_type}")
            print(f"   ✅ Migration cho '{col}' hoàn tất!")

    # --- Bảng 'auctions' ---
    try:
        auction_columns = [info[1] for info in cursor.execute(
            "PRAGMA table_info(auctions)").fetchall()]
        if 'channel_id' not in auction_columns:
            cursor.execute(
                "ALTER TABLE auctions ADD COLUMN channel_id INTEGER NOT NULL DEFAULT 0")
        if 'item_type' not in auction_columns:
            cursor.execute("ALTER TABLE auctions ADD COLUMN item_type TEXT")
        if 'item_id' not in auction_columns:
            cursor.execute("ALTER TABLE auctions ADD COLUMN item_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # --- Bảng 'achievements' ---
    try:
        ach_columns = [info[1] for info in cursor.execute(
            "PRAGMA table_info(achievements)").fetchall()]
        if 'badge_icon_url' in ach_columns:
            print(
                " > Migration: Chuyển đổi bảng 'achievements' từ huy hiệu ảnh sang emoji...")
            cursor.execute(
                "ALTER TABLE achievements RENAME TO achievements_old_temp")
            cursor.execute('''
            CREATE TABLE achievements (
                achievement_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
                achievement_type TEXT NOT NULL, target_value INTEGER NOT NULL,
                reward_coin INTEGER DEFAULT 0, reward_xp INTEGER DEFAULT 0,
                badge_emoji TEXT
            )''')
            cursor.execute('''
            INSERT INTO achievements (achievement_id, name, description, achievement_type, target_value, reward_coin, reward_xp)
            SELECT achievement_id, name, description, achievement_type, target_value, reward_coin, reward_xp
            FROM achievements_old_temp
            ''')
            cursor.execute("DROP TABLE achievements_old_temp")
            print("   ✅ Migration cho bảng 'achievements' hoàn tất!")
    except sqlite3.OperationalError:
        pass

    cursor.connection.commit()
    print("Di trú cơ sở dữ liệu hoàn tất.")


def populate_initial_quests():
    """Thêm các nhiệm vụ mẫu vào DB nếu chưa có. (Hàm này vẫn chạy đồng bộ lúc khởi tạo)"""
    quests_data = [
        ('daily_chat_25', 'Người Mới', 'Gửi 25 tin nhắn trong ngày.',
         'CHAT', 25, 250, 50, 'DAILY'),
        ('daily_chat_75', 'Thân Quen', 'Gửi 75 tin nhắn trong ngày.',
         'CHAT', 75, 750, 150, 'DAILY'),
        ('daily_chat_200', 'Cây Cổ Thụ', 'Gửi 200 tin nhắn trong ngày.',
         'CHAT', 200, 2000, 400, 'DAILY'),
        ('daily_chat_350', 'Chúa Tể Võ Mồm',
         'Gửi 350 tin nhắn trong ngày.', 'CHAT', 350, 3500, 700, 'DAILY'),
        ('daily_daily', 'Điểm Danh', 'Dùng lệnh ?daily 1 lần.',
         'DAILY_COMMAND', 1, 200, 50, 'DAILY'),
        ('daily_check_balance', 'Kiểm Tra Tài Sản',
         'Dùng lệnh ?balance để xem số dư.', 'CHECK_BALANCE', 1, 100, 20, 'DAILY'),
        ('daily_rps_win_1', 'Tập Sự', 'Thắng 1 ván Oẳn Tù Tì.',
         'RPS_WIN', 1, 300, 75, 'DAILY'),
        ('daily_rps_win_5', 'Cao Thủ Đấu Trí',
         'Thắng 5 ván Oẳn Tù Tì.', 'RPS_WIN', 5, 1500, 350, 'DAILY'),
        ('daily_rps_win_10', 'Vua Oẳn Tù Tì',
         'Thắng 10 ván Oẳn Tù Tì.', 'RPS_WIN', 10, 3500, 800, 'DAILY'),
        ('daily_flip_win_2', 'Thử Vận May',
         'Thắng 2 kèo cược ?flip.', 'FLIP_WIN', 2, 800, 150, 'DAILY'),
        ('daily_flip_win_7', 'Vua May Mắn', 'Thắng 7 kèo cược ?flip.',
         'FLIP_WIN', 7, 3000, 500, 'DAILY'),
        ('daily_flip_win_10', 'Con Cưng Của Thần May Mắn',
         'Thắng 10 kèo cược ?flip.', 'FLIP_WIN', 10, 5000, 1000, 'DAILY'),
        ('daily_spend_1000', 'Tiêu Tiền Là Đam Mê',
         'Tiêu 1,000 coin (mua đồ, cược, đấu giá).', 'COIN_SPEND', 1000, 500, 100, 'DAILY'),
        ('daily_spend_5000', 'Đại Gia', 'Tiêu 5,000 coin (mua đồ, cược, đấu giá).',
         'COIN_SPEND', 5000, 2500, 450, 'DAILY'),
        ('daily_spend_10000', 'Tay Chơi Thứ Thiệt',
         'Tiêu 10,000 coin (mua đồ, cược, đấu giá).', 'COIN_SPEND', 10000, 6000, 1200, 'DAILY'),
        ('daily_give_1000', 'Hào Phóng', 'Chuyển 1,000 coin cho người khác.',
         'GIVE_COIN', 1000, 300, 60, 'DAILY'),
        ('daily_give_5000', 'Nhà Từ Thiện', 'Chuyển 5,000 coin cho người khác.',
         'GIVE_COIN', 5000, 1500, 300, 'DAILY'),
        ('daily_buy_shop', 'Tín Đồ Mua Sắm',
         'Mua một vật phẩm bất kỳ từ ?shop.', 'SHOP_BUY', 1, 400, 80, 'DAILY'),
        ('daily_bid_3', 'Nhà Sưu Tầm', 'Trả giá trong một phiên đấu giá 3 lần.',
         'BID_AUCTION', 3, 700, 120, 'DAILY'),
        ('daily_loan', 'Túng Thiếu', 'Thực hiện một khoản vay bằng lệnh ?vay.',
         'LOAN_TAKEN', 1, 150, 30, 'DAILY'),
        ('daily_blackjack_win_1', 'Tân Binh Xì Dách',
         'Thắng 1 ván Blackjack.', 'BLACKJACK_WIN', 1, 500, 100, 'DAILY'),
        ('daily_blackjack_win_3', 'Tay Chơi Lão Làng',
         'Thắng 3 ván Blackjack.', 'BLACKJACK_WIN', 3, 2000, 400, 'DAILY'),
    ]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT OR IGNORE INTO quests VALUES (?, ?, ?, ?, ?, ?, ?, ?)", quests_data)
    conn.commit()
    conn.close()
    print(
        f" > Đã kiểm tra và thêm/cập nhật {len(quests_data)} nhiệm vụ mẫu vào database.")


def populate_initial_trivia():
    """Thêm các câu hỏi đố vui mẫu vào DB nếu chưa có."""
    trivia_data = [
        # ======================================================================
        # Lĩnh vực: GAME (Mở rộng)
        # ======================================================================
        ('Trong game Liên Minh Huyền Thoại, chiêu cuối của Yasuo có tên là gì?',
         '["Trăn Trối", "Bão Kiếm", "Quét Kiếm", "Đoạt Mệnh"]', 'Trăn Trối', 'Game'),
        ('Trong Valorant, chiêu cuối "Đại Băng Địa Chấn" (Glacial Cascade) thuộc về đặc vụ nào?',
         '["Sova", "Sage", "Breach", "Omen"]', 'Breach', 'Game'),
        ('Loại gỗ nào KHÔNG tồn tại trong Minecraft phiên bản gốc (không mod)?',
         '["Gỗ Sồi", "Gỗ Thông", "Gỗ Anh Đào", "Gỗ Tùng"]', 'Gỗ Tùng', 'Game'),
        ('Trong game "Among Us", nhiệm vụ nào thường bị nghi ngờ là "fake task" nhất?',
         '["Quẹt thẻ (Card Swipe)", "Sửa dây điện (Fix Wiring)", "Dọn lá cây (Clean O2 Filter)", "Đổ rác (Empty Garbage)"]', 'Quẹt thẻ (Card Swipe)', 'Game'),
        ('Tựa game nào có nhân vật chính tên là "Geralt of Rivia"?',
         '["The Witcher 3: Wild Hunt", "Elden Ring", "Skyrim", "Dark Souls"]', 'The Witcher 3: Wild Hunt', 'Game'),
        ('Trong CS:GO/CS2, khẩu súng nào đắt tiền nhất trong game?',
         '["AK-47", "AWP", "Negev", "M4A4"]', 'Negev', 'Game'),
        ('Nhân vật Mario trong series game của Nintendo làm nghề gì?',
         '["Thợ sửa ống nước", "Đầu bếp", "Bác sĩ", "Phi hành gia"]', 'Thợ sửa ống nước', 'Game'),
        ('Trong PUBG, "Sanhok" là bản đồ lấy cảm hứng từ khu vực nào?',
         '["Đông Nam Á", "Sa mạc Châu Phi", "Vùng băng tuyết Nga", "Châu Âu Trung Cổ"]', 'Đông Nam Á', 'Game'),
        ('Trong Genshin Impact, nguyên tố nào khắc chế nguyên tố Thủy (Hydro)?',
         '["Hỏa (Pyro)", "Lôi (Electro)", "Băng (Cryo)", "Tất cả các đáp án trên"]', 'Tất cả các đáp án trên', 'Game'),
        ('Tựa game nào được coi là "cha đẻ" của thể loại MOBA?',
         '["League of Legends", "Dota 2", "Smite", "DotA (map của Warcraft III)"]', 'DotA (map của Warcraft III)', 'Game'),
        ('Trong "The Last of Us", đại dịch toàn cầu bị gây ra bởi loại nấm nào?',
         '["Cordyceps", "Amanita", "Psilocybe", "Morel"]', 'Cordyceps', 'Game'),
        ('Nhân vật "Master Chief" là biểu tượng của dòng game nào?',
         '["Call of Duty", "Battlefield", "Halo", "Gears of War"]', 'Halo', 'Game'),
        ('Trong game "Pokémon", Pikachu là loài Pokémon hệ gì?',
         '["Lửa", "Nước", "Điện", "Cỏ"]', 'Điện', 'Game'),
        ('Thành phố "Los Santos" trong Grand Theft Auto V dựa trên thành phố nào ngoài đời thực?',
         '["New York", "Miami", "Los Angeles", "Chicago"]', 'Los Angeles', 'Game'),
        ('Trong Dota 2, "Aegis of the Immortal" cho phép người giữ nó làm gì?',
         '["Tăng sát thương", "Bất tử trong 5 giây", "Hồi sinh sau khi chết", "Tăng tốc độ chạy"]', 'Hồi sinh sau khi chết', 'Game'),

        # ======================================================================
        # Lĩnh vực: ĐỊA LÝ & DU LỊCH (Mở rộng)
        # ======================================================================
        ('Thủ đô của Úc là gì?',
         '["Sydney", "Melbourne", "Canberra", "Perth"]', 'Canberra', 'Địa lý'),
        ('Ngọn núi nào cao nhất thế giới?',
         '["K2", "Kangchenjunga", "Lhotse", "Everest"]', 'Everest', 'Địa lý'),
        ('Quốc gia nào có diện tích lớn nhất thế giới?',
         '["Canada", "Trung Quốc", "Mỹ", "Nga"]', 'Nga', 'Địa lý'),
        ('Thủ đô của Canada là gì?',
         '["Toronto", "Vancouver", "Montreal", "Ottawa"]', 'Ottawa', 'Địa lý'),
        ('Con sông nào dài nhất thế giới?',
         '["Sông Nile", "Sông Amazon", "Sông Dương Tử", "Sông Mississippi"]', 'Sông Nile', 'Địa lý'),
        ('Kim Tự Tháp Giza nổi tiếng nằm ở quốc gia nào?',
         '["Ả Rập Xê Út", "Ma Rốc", "Ai Cập", "Sudan"]', 'Ai Cập', 'Địa lý'),
        ('Thành phố nào được mệnh danh là "Thành phố không ngủ"?',
         '["Tokyo", "New York", "Las Vegas", "London"]', 'New York', 'Địa lý'),
        ('Quốc gia nào được mệnh danh là "Xứ sở Mặt trời mọc"?',
         '["Hàn Quốc", "Trung Quốc", "Nhật Bản", "Thái Lan"]', 'Nhật Bản', 'Địa lý'),
        ('Eo biển nào ngăn cách châu Á và châu Mỹ?',
         '["Eo biển Gibraltar", "Eo biển Malacca", "Eo biển Bering", "Eo biển Dover"]', 'Eo biển Bering', 'Địa lý'),
        ('Quốc gia nào có hình dạng giống như một chiếc ủng?',
         '["Hy Lạp", "Ý (Italy)", "Tây Ban Nha", "Na Uy"]', 'Ý (Italy)', 'Địa lý'),
        ('Thác nước cao nhất thế giới là thác nào?',
         '["Thác Niagara", "Thác Victoria", "Thác Angel", "Thác Iguazu"]', 'Thác Angel', 'Địa lý'),
        ('Sa mạc lớn nhất thế giới là sa mạc nào?',
         '["Sahara", "Gobi", "Kalahari", "Nam Cực"]', 'Nam Cực', 'Địa lý'),
        ('Vạn Lý Trường Thành nằm ở quốc gia nào?',
         '["Mông Cổ", "Nhật Bản", "Hàn Quốc", "Trung Quốc"]', 'Trung Quốc', 'Địa lý'),

        # ======================================================================
        # Lĩnh vực: KHOA HỌC & TỰ NHIÊN (Mở rộng)
        # ======================================================================
        ('Nguyên tố hóa học nào có ký hiệu là "Au"?',
         '["Bạc", "Nhôm", "Vàng", "Oxy"]', 'Vàng', 'Khoa học'),
        ('Hành tinh nào được biết đến với tên gọi "Hành tinh Đỏ"?',
         '["Sao Hỏa", "Sao Kim", "Sao Mộc", "Sao Thổ"]', 'Sao Hỏa', 'Khoa học'),
        ('Loài động vật nào trên cạn chạy nhanh nhất?',
         '["Sư tử", "Linh dương", "Báo Gêpa", "Ngựa vằn"]', 'Báo Gêpa', 'Khoa học'),
        ('Nước chiếm bao nhiêu phần trăm bề mặt Trái Đất?',
         '["Khoảng 50%", "Khoảng 60%", "Khoảng 70%", "Khoảng 80%"]', 'Khoảng 70%', 'Khoa học'),
        ('Công thức hóa học của nước là gì?',
         '["CO2", "O2", "H2O", "NaCl"]', 'H2O', 'Khoa học'),
        ('Âm thanh di chuyển nhanh nhất trong môi trường nào?',
         '["Không khí", "Nước", "Chân không", "Chất rắn"]', 'Chất rắn', 'Khoa học'),
        ('Nguyên tố nào phổ biến nhất trong vũ trụ?',
         '["Oxy", "Carbon", "Hydro", "Heli"]', 'Hydro', 'Khoa học'),
        ('Ký hiệu hóa học của Thủy ngân là gì?',
         '["Ag", "Pb", "Hg", "Sn"]', 'Hg', 'Khoa học'),
        ('Lực nào giữ cho các hành tinh quay quanh Mặt trời?',
         '["Lực hấp dẫn", "Lực từ", "Lực hạt nhân", "Lực ma sát"]', 'Lực hấp dẫn', 'Khoa học'),
        ('Cá voi xanh, loài động vật lớn nhất hành tinh, thuộc lớp nào?',
         '["Lớp Cá", "Lớp Bò sát", "Lớp Lưỡng cư", "Lớp Thú (Động vật có vú)"]', 'Lớp Thú (Động vật có vú)', 'Khoa học'),
        ('Cây nào cao nhất thế giới?',
         '["Cây Bao báp", "Cây Bạch đàn", "Cây Gỗ đỏ (Redwood)", "Cây Tùng"]', 'Cây Gỗ đỏ (Redwood)', 'Khoa học'),
        ('Con người có bao nhiêu cặp nhiễm sắc thể?',
         '["22", "23", "46", "48"]', '23', 'Khoa học'),
        ('Khí nào cần thiết cho sự sống của thực vật (quang hợp)?',
         '["Oxy (O2)", "Nitơ (N2)", "Carbon Dioxide (CO2)", "Hydro (H2)"]', 'Carbon Dioxide (CO2)', 'Khoa học'),

        # ======================================================================
        # Lĩnh vực: LỊCH SỬ & THẦN THOẠI (Mở rộng)
        # ======================================================================
        ('Trong thần thoại Hy Lạp, ai là vị thần của biển cả?',
         '["Zeus", "Hades", "Apollo", "Poseidon"]', 'Poseidon', 'Lịch sử & Thần thoại'),
        ('Ai là vị vua đầu tiên của nhà Nguyễn ở Việt Nam?',
         '["Vua Quang Trung", "Vua Gia Long", "Vua Minh Mạng", "Vua Tự Đức"]', 'Vua Gia Long', 'Lịch sử & Thần thoại'),
        ('Vị tướng nào đã lãnh đạo trận chiến Điện Biên Phủ năm 1954?',
         '["Võ Nguyên Giáp", "Hoàng Văn Thái", "Lê Trọng Tấn", "Trần Văn Trà"]', 'Võ Nguyên Giáp', 'Lịch sử & Thần thoại'),
        ('Trong thần thoại Bắc Âu, "Mjolnir" là tên cây búa của vị thần nào?',
         '["Odin", "Loki", "Thor", "Heimdall"]', 'Thor', 'Lịch sử & Thần thoại'),
        ('Thành phố Pompeii bị chôn vùi bởi ngọn núi lửa nào?',
         '["Etna", "Vesuvius", "Stromboli", "Fuji"]', 'Vesuvius', 'Lịch sử & Thần thoại'),
        ('Ai là nữ pharaoh nổi tiếng nhất của Ai Cập cổ đại?',
         '["Nefertiti", "Cleopatra", "Hatshepsut", "Ankhesenamun"]', 'Cleopatra', 'Lịch sử & Thần thoại'),
        ('Nhà thám hiểm nào được cho là người châu Âu đầu tiên tìm ra châu Mỹ?',
         '["Ferdinand Magellan", "Vasco da Gama", "Christopher Columbus", "Marco Polo"]', 'Christopher Columbus', 'Lịch sử & Thần thoại'),
        ('Cuộc chiến tranh thế giới thứ nhất bắt đầu vào năm nào?',
         '["1905", "1914", "1920", "1939"]', '1914', 'Lịch sử & Thần thoại'),
        ('Ai là người đã viết ra "Binh pháp Tôn Tử"?',
         '["Khổng Tử", "Lão Tử", "Tôn Tử", "Tào Tháo"]', 'Tôn Tử', 'Lịch sử & Thần thoại'),

        # ======================================================================
        # Lĩnh vực: VĂN HỌC & PHIM ẢNH (Mở rộng)
        # ======================================================================
        ('Trong series phim Harry Potter, con gia tinh nhà Malfoy tên là gì?',
         '["Kreacher", "Winky", "Dobby", "Hokey"]', 'Dobby', 'Văn học & Phim'),
        ('Bộ phim nào đã giành giải "Phim hay nhất" tại Oscar năm 2020?',
         '["1917", "Joker", "Once Upon a Time in Hollywood", "Parasite (Ký sinh trùng)"]', 'Parasite (Ký sinh trùng)', 'Văn học & Phim'),
        ('Trong "Chúa tể những chiếc nhẫn", có tổng cộng bao nhiêu chiếc nhẫn quyền lực được tạo ra ban đầu?',
         '["1", "9", "19", "20"]', '20', 'Văn học & Phim'),
        ('Ai là tác giả của bộ truyện "Dế Mèn phiêu lưu ký"?',
         '["Nam Cao", "Ngô Tất Tố", "Tô Hoài", "Vũ Trọng Phụng"]', 'Tô Hoài', 'Văn học & Phim'),
        ('Trong vũ trụ Marvel, viên đá vô cực nào cho phép người dùng du hành thời gian?',
         '["Đá Không Gian (Space Stone)", "Đá Thời Gian (Time Stone)", "Đá Thực Tại (Reality Stone)", "Đá Sức Mạnh (Power Stone)"]', 'Đá Thời Gian (Time Stone)', 'Văn học & Phim'),
        ('Bộ phim "Mắt Biếc" được chuyển thể từ tác phẩm của nhà văn nào?',
         '["Nguyễn Nhật Ánh", "Nam Cao", "Nguyễn Ngọc Tư", "Trang Hạ"]', 'Nguyễn Nhật Ánh', 'Văn học & Phim'),
        ('Trong "Star Wars", câu nói "May the Force be with you" có ý nghĩa gì?',
         '["Chúc may mắn", "Mạnh mẽ lên", "Nguyện Thần lực ở bên bạn", "Hãy cẩn thận"]', 'Nguyện Thần lực ở bên bạn', 'Văn học & Phim'),
        ('Nhân vật thám tử Sherlock Holmes sống ở địa chỉ nào tại London?',
         '["221B phố Baker", "10 phố Downing", "42 phố Wallaby", "12 phố Grimmauld"]', '221B phố Baker', 'Văn học & Phim'),
        ('Bộ phim nào có câu thoại nổi tiếng "I\'ll be back"?',
         '["Rambo", "Die Hard", "The Terminator (Kẻ hủy diệt)", "Predator"]', 'The Terminator (Kẻ hủy diệt)', 'Văn học & Phim'),
        ('Trong truyện cổ tích "Nàng Bạch Tuyết và bảy chú lùn", chú lùn nào hay hắt xì?',
         '["Dopey (Ngốc Nghếch)", "Grumpy (Gắt Gỏng)", "Sleepy (Ngái Ngủ)", "Sneezy (Hắt Xì)"]', 'Sneezy (Hắt Xì)', 'Văn học & Phim'),

        # ======================================================================
        # Lĩnh vực: ÂM NHẠC (Mở rộng)
        # ======================================================================
        ('Bài hát "See You Again" là nhạc phim của bộ phim nào?',
         '["Fast & Furious 7", "The Avengers", "Avatar", "Titanic"]', 'Fast & Furious 7', 'Âm nhạc'),
        ('Ca khúc nào của Sơn Tùng M-TP đạt 100 triệu view nhanh nhất trên YouTube Việt Nam?',
         '["Lạc Trôi", "Nơi Này Có Anh", "Hãy Trao Cho Anh", "Chúng Ta Không Thuộc Về Nhau"]', 'Hãy Trao Cho Anh', 'Âm nhạc'),
        ('Nhóm nhạc K-Pop nào được mệnh danh là "Những vị vua của K-Pop"?',
         '["EXO", "BIGBANG", "BTS", "NCT"]', 'BIGBANG', 'Âm nhạc'),
        ('Ai được mệnh danh là "Ông hoàng nhạc Pop"?',
         '["Elvis Presley", "Michael Jackson", "Freddie Mercury", "Elton John"]', 'Michael Jackson', 'Âm nhạc'),
        ('Nhạc cụ nào có 88 phím?',
         '["Guitar", "Violin", "Piano", "Sáo"]', 'Piano', 'Âm nhạc'),
        ('Taylor Swift nổi tiếng với thể loại nhạc nào ở giai đoạn đầu sự nghiệp?',
         '["Pop", "Rock", "Country (Đồng quê)", "Hip Hop"]', 'Country (Đồng quê)', 'Âm nhạc'),
        ('Nhóm nhạc huyền thoại The Beatles đến từ thành phố nào của Anh?',
         '["London", "Manchester", "Liverpool", "Birmingham"]', 'Liverpool', 'Âm nhạc'),
        ('Trong Rap Việt, ai là huấn luyện viên có thí sinh vô địch cả 2 mùa đầu tiên?',
         '["Binz", "Wowy", "Karik", "Suboi"]', 'Karik', 'Âm nhạc'),

        # ======================================================================
        # Lĩnh vực: ĐỐ VUI IQ & MẸO VẶT (Mở rộng)
        # ======================================================================
        ('Câu đố mẹo: Con gì đầu dê mình ốc?',
         '["Con ốc", "Con dê", "Con dốc", "Một loài sinh vật lạ"]', 'Con dốc', 'Đố Vui IQ'),
        ('Cái gì luôn đến nhưng không bao giờ đến nơi?',
         '["Ngày mai", "Quá khứ", "Cơn mưa", "Giấc mơ"]', 'Ngày mai', 'Đố Vui IQ'),
        ('Trong bảng chữ cái tiếng Việt, chữ cái nào đứng cuối cùng?',
         '["Y", "X", "W", "V"]', 'Y', 'Đố Vui IQ'),
        ('Tháng nào có 28 ngày?',
         '["Tháng 2", "Tháng 4", "Tháng 6", "Tất cả các tháng"]', 'Tất cả các tháng', 'Đố Vui IQ'),
        ('Có 1 đàn chim đậu trên cành, người thợ săn bắn "Rằm". Hỏi chết mấy con?',
         '["1 con", "15 con", "0 con", "Cả đàn"]', '15 con', 'Đố Vui IQ'),
        ('Cái gì bạn có thể giữ sau khi đã đưa nó cho người khác?',
         '["Tiền bạc", "Bí mật", "Lời hứa", "Đồ vật"]', 'Lời hứa', 'Đố Vui IQ'),
        ('Một người nông dân có 17 con cừu, tất cả trừ 9 con bị chết. Hỏi ông còn lại bao nhiêu con?',
         '["8 con", "17 con", "9 con", "0 con"]', '9 con', 'Đố Vui IQ'),
        ('Bác sĩ đưa cho bạn 3 viên thuốc và bảo bạn uống mỗi viên cách nhau nửa giờ. Bạn sẽ mất bao lâu để uống hết?',
         '["Nửa giờ", "Một giờ", "Một giờ rưỡi", "Hai giờ"]', 'Một giờ', 'Đố Vui IQ'),
        ('Cái gì đi lên nhưng không bao giờ đi xuống?',
         '["Tuổi của bạn", "Nhiệt độ", "Giá xăng", "Mặt trời"]', 'Tuổi của bạn', 'Đố Vui IQ'),

        # ======================================================================
        # Lĩnh vực: ANIME & MANGA (Mở rộng)
        # ======================================================================
        ('Trong "One Piece", trái ác quỷ của Monkey D. Luffy tên là gì?',
         '["Gomu Gomu no Mi", "Mera Mera no Mi", "Ope Ope no Mi", "Gura Gura no Mi"]', 'Gomu Gomu no Mi', 'Anime & Manga'),
        ('Trong "Naruto", Làng Lá có tên chính thức là gì?',
         '["Konohagakure", "Sunagakure", "Kirigakure", "Kumogakure"]', 'Konohagakure', 'Anime & Manga'),
        ('Tác giả của bộ manga "Dragon Ball" (7 Viên Ngọc Rồng) là ai?',
         '["Masashi Kishimoto", "Eiichiro Oda", "Akira Toriyama", "Hajime Isayama"]', 'Akira Toriyama', 'Anime & Manga'),
        ('Trong "Attack on Titan", Titan Shifter nào có khả năng hóa cứng cơ thể?',
         '["Titan Thiết Giáp", "Titan Đại Hình", "Titan Nữ Hình", "Tất cả các đáp án trên"]', 'Tất cả các đáp án trên', 'Anime & Manga'),
        ('Bộ anime nào có nhân vật chính tên là "Saitama"?',
         '["My Hero Academia", "Jujutsu Kaisen", "One-Punch Man", "Demon Slayer"]', 'One-Punch Man', 'Anime & Manga'),
        ('Trong "Demon Slayer" (Kimetsu no Yaiba), em gái của Tanjiro tên là gì?',
         '["Shinobu", "Kanao", "Nezuko", "Mitsuri"]', 'Nezuko', 'Anime & Manga'),
        ('Bộ anime "Spirited Away" (Vùng Đất Linh Hồn) là tác phẩm của studio nào?',
         '["Kyoto Animation", "Madhouse", "Ufotable", "Studio Ghibli"]', 'Studio Ghibli', 'Anime & Manga'),
        ('Trong "Jujutsu Kaisen", "Vô Lượng Không Xứ" là Lãnh địa của ai?',
         '["Sukuna", "Gojo Satoru", "Megumi Fushiguro", "Itadori Yuji"]', 'Gojo Satoru', 'Anime & Manga'),
        ('Trong "Death Note", "L" là biệt danh của ai?',
         '["Light Yagami", "Ryuk", "L Lawliet", "Misa Amane"]', 'L Lawliet', 'Anime & Manga'),

        # ======================================================================
        # Lĩnh vực: KIẾN THỨC CHUNG & ĐỘC LẠ (Mới)
        # ======================================================================
        ('Màu sắc nào KHÔNG có trong lá cờ Olympic?',
         '["Đen", "Vàng", "Xanh lá", "Tím"]', 'Tím', 'Kiến thức chung'),
        ('Con người có bao nhiêu giác quan cơ bản?',
         '["3", "5", "6", "7"]', '5', 'Kiến thức chung'),
        ('Website nào được ra mắt đầu tiên trong số các website sau?',
         '["Facebook", "YouTube", "Google", "Twitter"]', 'Google', 'Kiến thức chung'),
        ('"Checkmate" là thuật ngữ kết thúc một ván cờ gì?',
         '["Cờ Tỷ Phú", "Cờ Vua", "Cờ Tướng", "Cờ Caro"]', 'Cờ Vua', 'Kiến thức chung'),
        ('Trong bảng mã Morse, ba dấu chấm (...) đại diện cho chữ cái nào?',
         '["A", "O", "S", "E"]', 'S', 'Kiến thức chung'),
        ('Một "baker\'s dozen" (tá của thợ làm bánh) có bao nhiêu chiếc?',
         '["10", "12", "13", "24"]', '13', 'Kiến thức chung'),
        ('Logo của hãng xe Lamborghini có hình con vật gì?',
         '["Ngựa", "Báo", "Sư tử", "Bò tót"]', 'Bò tót', 'Kiến thức chung'),
        ('Sân bay nào có mã IATA là "LAX"?',
         '["Sân bay London Heathrow", "Sân bay Los Angeles", "Sân bay Charles de Gaulle", "Sân bay Nội Bài"]', 'Sân bay Los Angeles', 'Kiến thức chung'),
        ('Loại cà phê nào đắt nhất thế giới, được làm từ phân của một loài động vật?',
         '["Arabica", "Robusta", "Cà phê Chồn (Kopi Luwak)", "Espresso"]', 'Cà phê Chồn (Kopi Luwak)', 'Kiến thức chung'),
        ('Mật ong có thể bị hỏng không?',
         '["Có, sau 1 năm", "Có, sau 5 năm", "Không bao giờ hỏng", "Có, nếu để trong tủ lạnh"]', 'Không bao giờ hỏng', 'Kiến thức chung'),
    ]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT OR IGNORE INTO trivia_questions (question_text, options, correct_answer, category) VALUES (?, ?, ?, ?)", trivia_data)
    conn.commit()
    conn.close()
    print(
        f" > Đã kiểm tra và thêm/cập nhật {len(trivia_data)} câu hỏi đố vui vào database.")


def populate_initial_achievements():
    """Cập nhật các thành tựu. (Hàm này vẫn chạy đồng bộ lúc khởi tạo)"""
    achievements_data_with_emoji = {
        'chat_master': ('Bậc Thầy Tán Gẫu', 'Gửi 1,000,000 tin nhắn.', 'CHAT', 1000000, 50000, 5000, '💬'),
        'rps_king': ('Vua Oẳn Tù Tì', 'Thắng 1000 trận Oẳn Tù Tì.', 'RPS_WIN', 1000, 40000, 5000, '✌️'),
        'big_spender': ('Đại Gia', 'Tiêu 10,000,000 coin.', 'COIN_SPEND', 10000000, 100000, 10000, '💰'),
        'level_god': ('Thần Cấp Độ', 'Đạt cấp 500.', 'REACH_LEVEL', 500, 100000, 0, '⭐'),
        'shopaholic': ('Tín Đồ Mua Sắm', 'Thực hiện 1000 lần mua hàng.', 'SHOP_BUY', 1000, 100000, 5000, '🛍️'),
        'auction_tycoon': ('Trùm Đấu Giá', 'Thực hiện 1000 lần trả giá.', 'BID_AUCTION', 50000, 15000, 4000, '🔨'),
        'debt_is_a_tool': ('Vay Nợ Là Một Công Cụ', 'Thực hiện 500 lần vay tiền.', 'LOAN_TAKEN', 500, 50000, 5000, '💸'),
        'blackjack_master': ('Thần Bài Xì Dách', 'Thắng 1000 ván Blackjack.', 'BLACKJACK_WIN', 1000, 80000, 10000, '🃏'),
    }
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for ach_id, data in achievements_data_with_emoji.items():
        cursor.execute(
            "INSERT OR REPLACE INTO achievements VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (ach_id,) + data)
    conn.commit()
    conn.close()
    print(
        f" > Đã kiểm tra và cập nhật emoji cho {len(achievements_data_with_emoji)} thành tựu.")


def init_db():
    """Hàm khởi tạo database, chỉ chạy 1 lần khi bot khởi động. (Vẫn dùng sqlite3 đồng bộ)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, xp REAL DEFAULT 0, level INTEGER DEFAULT 1, coins INTEGER DEFAULT 0 NOT NULL, daily_timestamp TEXT, PRIMARY KEY (user_id, guild_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (warning_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, reason TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS server_configs (guild_id INTEGER PRIMARY KEY, welcome_channel_id INTEGER, goodbye_channel_id INTEGER, announcement_channel_id INTEGER, command_channel_id INTEGER, muted_role_id INTEGER, luck_role_id INTEGER, top_role_id INTEGER, vip_role_id INTEGER, debtor_role_id INTEGER, create_vc_channel_id INTEGER, log_channel_id INTEGER, main_chat_channel_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS level_roles (guild_id INTEGER NOT NULL, level INTEGER NOT NULL, role_id INTEGER NOT NULL, PRIMARY KEY (guild_id, level))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS lottery_tickets (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, tickets_bought INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, item_id TEXT NOT NULL, quantity INTEGER DEFAULT 1, PRIMARY KEY (guild_id, user_id, item_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS active_effects (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, effect_type TEXT NOT NULL, expiry_timestamp TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, effect_type))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS temporary_roles (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL, expiry_timestamp TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, role_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS shop_roles (guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL, price INTEGER NOT NULL, duration_seconds INTEGER NOT NULL, description TEXT, PRIMARY KEY (guild_id, role_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS auctions (guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER PRIMARY KEY, item_name TEXT NOT NULL, item_type TEXT, item_id INTEGER, seller_id INTEGER NOT NULL, start_price INTEGER DEFAULT 0, current_bid INTEGER DEFAULT 0, highest_bidder_id INTEGER, end_timestamp TEXT NOT NULL, is_active INTEGER DEFAULT 1)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS loans (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, repayment_amount INTEGER NOT NULL, due_date TEXT NOT NULL, PRIMARY KEY (user_id, guild_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS quests (quest_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, quest_type TEXT NOT NULL, target_value INTEGER NOT NULL, reward_coin INTEGER DEFAULT 0, reward_xp INTEGER DEFAULT 0, frequency TEXT DEFAULT 'DAILY')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_quests (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, quest_id TEXT NOT NULL, progress INTEGER DEFAULT 0, is_completed INTEGER DEFAULT 0, assigned_date TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, quest_id), FOREIGN KEY (quest_id) REFERENCES quests (quest_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS achievements (achievement_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, achievement_type TEXT NOT NULL, target_value INTEGER NOT NULL, reward_coin INTEGER DEFAULT 0, reward_xp INTEGER DEFAULT 0, badge_emoji TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_achievements (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, achievement_id TEXT NOT NULL, progress INTEGER DEFAULT 0, unlocked_timestamp TEXT, PRIMARY KEY (user_id, guild_id, achievement_id), FOREIGN KEY (achievement_id) REFERENCES achievements (achievement_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS relationships (guild_id INTEGER NOT NULL, user1_id INTEGER NOT NULL, user2_id INTEGER NOT NULL, relationship_type TEXT NOT NULL, timestamp TEXT NOT NULL, PRIMARY KEY (guild_id, user1_id, user2_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS world_boss (guild_id INTEGER PRIMARY KEY, boss_name TEXT NOT NULL, current_hp INTEGER NOT NULL, max_hp INTEGER NOT NULL, message_id INTEGER, channel_id INTEGER, spawned_by_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS boss_attackers (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, total_damage INTEGER DEFAULT 0, last_attack_timestamp TEXT, PRIMARY KEY (guild_id, user_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS pinned_messages (pin_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, author_id INTEGER NOT NULL, message_content TEXT, embed_data TEXT, last_message_id INTEGER)''')
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS temp_voice_channels (guild_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, channel_id INTEGER PRIMARY KEY)''')
    cursor.execute(
        '''CREATE TABLE IF NOT EXISTS qotd (question_id INTEGER PRIMARY KEY AUTOINCREMENT, question_text TEXT NOT NULL, is_used INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS trivia_questions (question_id INTEGER PRIMARY KEY AUTOINCREMENT, question_text TEXT NOT NULL, options TEXT NOT NULL, correct_answer TEXT NOT NULL, category TEXT, is_used INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS active_trivia (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, correct_answer TEXT NOT NULL, expiry_timestamp TEXT NOT NULL, answered_users_json TEXT DEFAULT '[]')''')
    run_migrations(cursor)
    populate_initial_quests()
    populate_initial_achievements()
    populate_initial_trivia()

    conn.commit()
    conn.close()
    print("Database đã được khởi tạo và kiểm tra.")


# --- TỪ ĐÂY TRỞ XUỐNG, TẤT CẢ HÀM TƯƠNG TÁC VỚI DB ĐỀU LÀ ASYNC ---

async def add_shop_role(guild_id, role_id, price, duration_seconds, description):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO shop_roles (guild_id, role_id, price, duration_seconds, description) 
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, role_id) DO UPDATE SET
            price=excluded.price,
            duration_seconds=excluded.duration_seconds,
            description=excluded.description
        ''', (guild_id, role_id, price, duration_seconds, description))
        await db.commit()


async def get_or_create_user(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
            user = await cursor.fetchone()

        if not user:
            await db.execute("INSERT INTO users (user_id, guild_id, coins) VALUES (?, ?, ?)", (user_id, guild_id, 500))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
                user = await cursor.fetchone()
            # Phải gọi hàm async bằng await
            await assign_all_achievements_to_user(user_id, guild_id)
            # Truy vấn lại user để đảm bảo dữ liệu mới nhất
            async with db.execute("SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
                user = await cursor.fetchone()

        return dict(user)


async def update_user_xp(user_id, guild_id, xp_to_add, *, db_conn=None):
    # Hàm này có thể dùng kết nối có sẵn (db_conn) hoặc tự tạo mới
    if db_conn:
        await db_conn.execute("UPDATE users SET xp = xp + ? WHERE user_id = ? AND guild_id = ?", (xp_to_add, user_id, guild_id))
        # Không commit ở đây, để hàm gọi bên ngoài commit
    else:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET xp = xp + ? WHERE user_id = ? AND guild_id = ?", (xp_to_add, user_id, guild_id))
            await db.commit()


async def update_user_level(user_id, guild_id, new_level):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET level = ?, xp = 0 WHERE user_id = ? AND guild_id = ?", (new_level, user_id, guild_id))
        await db.commit()


async def update_coins(user_id, guild_id, amount, *, db_conn=None):
    # Hàm này có thể dùng kết nối có sẵn (db_conn) hoặc tự tạo mới
    if db_conn:
        await db_conn.execute("UPDATE users SET coins = coins + ? WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
        # Không commit ở đây, để hàm gọi bên ngoài commit
    else:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
            await db.commit()


async def get_user_inventory(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT item_id, quantity FROM inventory WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
            rows = await cursor.fetchall()
            return {item_id: quantity for item_id, quantity in rows}


async def add_item_to_inventory(user_id, guild_id, item_id, quantity=1):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO inventory (user_id, guild_id, item_id, quantity) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET quantity = quantity + ?", (user_id, guild_id, item_id, quantity, quantity))
        await db.commit()


async def remove_item_from_inventory(user_id, guild_id, item_id, quantity=1):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT quantity FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", (user_id, guild_id, item_id)) as cursor:
            item = await cursor.fetchone()

        if not item or item['quantity'] < quantity:
            return False

        if item['quantity'] > quantity:
            await db.execute("UPDATE inventory SET quantity = quantity - ? WHERE user_id = ? AND guild_id = ? AND item_id = ?", (quantity, user_id, guild_id, item_id))
        else:
            await db.execute("DELETE FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", (user_id, guild_id, item_id))

        await db.commit()
        return True


async def check_inventory_item(user_id, guild_id, item_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT quantity FROM inventory WHERE user_id = ? AND guild_id = ? AND item_id = ?", (user_id, guild_id, item_id)) as cursor:
            item = await cursor.fetchone()
        return item['quantity'] if item else 0


async def remove_shop_role(guild_id, role_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM shop_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id))
        count = cursor.rowcount
        await db.commit()
        return count


async def get_shop_roles(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_roles WHERE guild_id = ?", (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_shop_role(guild_id, role_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)) as cursor:
            role = await cursor.fetchone()
        return dict(role) if role else None


async def add_active_effect(user_id, guild_id, effect_type, expiry_timestamp_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO active_effects (user_id, guild_id, effect_type, expiry_timestamp) VALUES (?, ?, ?, ?)", (user_id, guild_id, effect_type, expiry_timestamp_str))
        await db.commit()


async def get_user_active_effect(user_id, guild_id, effect_type):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM active_effects WHERE user_id = ? AND guild_id = ? AND effect_type = ?", (user_id, guild_id, effect_type)) as cursor:
            effect = await cursor.fetchone()
        if effect and datetime.datetime.fromisoformat(effect['expiry_timestamp']) > datetime.datetime.now(datetime.timezone.utc):
            return dict(effect)
        return None


async def add_temporary_role(user_id, guild_id, role_id, expiry_timestamp_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO temporary_roles (user_id, guild_id, role_id, expiry_timestamp) VALUES (?, ?, ?, ?)", (user_id, guild_id, role_id, expiry_timestamp_str))
        await db.commit()


async def remove_temporary_role(user_id, guild_id, role_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM temporary_roles WHERE user_id = ? AND guild_id = ? AND role_id = ?", (user_id, guild_id, role_id))
        await db.commit()


async def get_expired_items(table_name):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with db.execute(f"SELECT * FROM {table_name} WHERE expiry_timestamp < ?", (now_str,)) as cursor:
            items = await cursor.fetchall()
            return [dict(row) for row in items]


async def clear_expired_items(table_name, primary_keys, items_to_clear):
    if not items_to_clear:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        placeholders = ' AND '.join([f"{key} = ?" for key in primary_keys])
        keys_to_delete = [tuple(item[key] for key in primary_keys)
                          for item in items_to_clear]
        await db.executemany(f"DELETE FROM {table_name} WHERE {placeholders}", keys_to_delete)
        await db.commit()


async def update_daily_timestamp(user_id, guild_id, timestamp_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET daily_timestamp = ? WHERE user_id = ? AND guild_id = ?", (timestamp_str, user_id, guild_id))
        await db.commit()


async def get_leaderboard(guild_id, limit=100):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, xp, level, coins FROM users WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT ?", (guild_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_lottery_pot(guild_id):
    base_prize = 20000
    try:
        from cogs.economy import SHOP_ITEMS
        price = SHOP_ITEMS['lottery_ticket']['price']
    except (ImportError, KeyError):
        price = 100

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT SUM(tickets_bought) FROM lottery_tickets WHERE guild_id = ?", (guild_id,)) as cursor:
            total_tickets = (await cursor.fetchone())[0] or 0
    return (total_tickets * price) + base_prize


async def get_lottery_participants(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, tickets_bought FROM lottery_tickets WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchall()


async def add_lottery_tickets(guild_id, user_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO lottery_tickets (guild_id, user_id, tickets_bought) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET tickets_bought = tickets_bought + ?", (guild_id, user_id, amount, amount))
        await db.commit()


async def clear_lottery(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM lottery_tickets WHERE guild_id = ?", (guild_id,))
        await db.commit()


async def add_warning(user_id, guild_id, moderator_id, reason):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO warnings (user_id, guild_id, moderator_id, reason) VALUES (?, ?, ?, ?)", (user_id, guild_id, moderator_id, reason))
        await db.commit()


async def get_warnings(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT moderator_id, reason, timestamp FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY timestamp DESC", (user_id, guild_id)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def clear_warnings(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM warnings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        count = cursor.rowcount
        await db.commit()
        return count


async def get_or_create_config(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM server_configs WHERE guild_id = ?", (guild_id,)) as cursor:
            config_row = await cursor.fetchone()
        if not config_row:
            await db.execute("INSERT INTO server_configs (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
            async with db.execute("SELECT * FROM server_configs WHERE guild_id = ?", (guild_id,)) as cursor:
                config_row = await cursor.fetchone()
        return dict(config_row)


async def update_config(guild_id, key, value):
    await get_or_create_config(guild_id)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE server_configs SET {key} = ? WHERE guild_id = ?", (value, guild_id))
        await db.commit()


async def add_level_role(guild_id, level, role_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)", (guild_id, level, role_id))
        await db.commit()


async def remove_level_role(guild_id, level):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (guild_id, level))
        count = cursor.rowcount
        await db.commit()
        return count


async def get_level_roles(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT level, role_id FROM level_roles WHERE guild_id = ? ORDER BY level DESC", (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return {level: role_id for level, role_id in rows}


async def create_auction(guild_id, channel_id, message_id, item_name, item_type, item_id, seller_id, start_price, end_timestamp_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO auctions (guild_id, channel_id, message_id, item_name, item_type, item_id, seller_id, start_price, current_bid, end_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, channel_id, message_id, item_name, item_type, item_id, seller_id, start_price, start_price, end_timestamp_str))
        await db.commit()


async def get_auction(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM auctions WHERE message_id = ?", (message_id,)) as cursor:
            auction = await cursor.fetchone()
        return dict(auction) if auction else None


async def update_bid(message_id, new_bid, bidder_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            UPDATE auctions 
            SET current_bid = ?, highest_bidder_id = ?
            WHERE message_id = ?
        ''', (new_bid, bidder_id, message_id))
        await db.commit()


async def get_active_auctions():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM auctions WHERE is_active = 1") as cursor:
            auctions = await cursor.fetchall()
        return [dict(row) for row in auctions]


async def end_auction(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE auctions SET is_active = 0 WHERE message_id = ?", (message_id,))
        await db.commit()


async def create_loan(user_id, guild_id, repayment_amount, due_date_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO loans (user_id, guild_id, repayment_amount, due_date) VALUES (?, ?, ?, ?)", (user_id, guild_id, repayment_amount, due_date_str))
        await db.commit()


async def get_loan(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM loans WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
            loan = await cursor.fetchone()
        return dict(loan) if loan else None


async def delete_loan(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM loans WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        await db.commit()


async def get_all_loans():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM loans") as cursor:
            loans = await cursor.fetchall()
        return [dict(row) for row in loans]


async def get_quests_by_frequency(frequency):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM quests WHERE frequency = ?", (frequency,)) as cursor:
            quests = await cursor.fetchall()
        return [dict(row) for row in quests]


async def assign_user_quests(user_id, guild_id, quest_ids, assigned_date_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM user_quests WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        tasks = [(user_id, guild_id, q_id, assigned_date_str)
                 for q_id in quest_ids]
        await db.executemany("INSERT INTO user_quests (user_id, guild_id, quest_id, assigned_date) VALUES (?, ?, ?, ?)", tasks)
        await db.commit()


async def get_user_quests(user_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT uq.*, q.name, q.description, q.quest_type, q.target_value, q.reward_coin, q.reward_xp
            FROM user_quests uq
            JOIN quests q ON uq.quest_id = q.quest_id
            WHERE uq.user_id = ? AND uq.guild_id = ?
        """, (user_id, guild_id)) as cursor:
            quests = await cursor.fetchall()
        return [dict(row) for row in quests]


async def update_quest_progress(user_id, guild_id, quest_type, value_to_add=1):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT uq.quest_id, uq.progress, q.target_value
            FROM user_quests uq
            JOIN quests q ON uq.quest_id = q.quest_id
            WHERE uq.user_id = ? AND uq.guild_id = ? AND q.quest_type = ? AND uq.is_completed = 0
        """, (user_id, guild_id, quest_type)) as cursor:
            user_quests_to_update = await cursor.fetchall()

        for quest in user_quests_to_update:
            new_progress = quest['progress'] + value_to_add
            await db.execute("UPDATE user_quests SET progress = ? WHERE user_id = ? AND guild_id = ? AND quest_id = ?", (new_progress, user_id, guild_id, quest['quest_id']))
            if new_progress >= quest['target_value']:
                await db.execute("UPDATE user_quests SET is_completed = 1 WHERE user_id = ? AND guild_id = ? AND quest_id = ?", (user_id, guild_id, quest['quest_id']))
        await db.commit()


async def claim_quest_reward(user_id, guild_id, quest_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM user_quests WHERE user_id = ? AND guild_id = ? AND quest_id = ?", (user_id, guild_id, quest_id))
        await db.commit()


async def assign_all_achievements_to_user(user_id, guild_id):
    """Gán tất cả các thành tựu mặc định cho người dùng khi họ được tạo."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT achievement_id FROM achievements") as cursor:
            all_achievement_ids = [row['achievement_id'] for row in await cursor.fetchall()]

        user_ach_data = [(user_id, guild_id, ach_id)
                         for ach_id in all_achievement_ids]
        await db.executemany("INSERT OR IGNORE INTO user_achievements (user_id, guild_id, achievement_id) VALUES (?, ?, ?)", user_ach_data)
        await db.commit()


async def update_achievement_progress(user_id, guild_id, achievement_type, value_to_add=1):
    """Cập nhật tiến trình cho một loại thành tựu."""
    async with aiosqlite.connect(DB_NAME) as db:  # Mở một kết nối duy nhất
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ua.achievement_id, ua.progress, a.target_value, a.name, a.reward_coin, a.reward_xp
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.achievement_id
            WHERE ua.user_id = ? AND ua.guild_id = ? AND a.achievement_type = ? AND ua.unlocked_timestamp IS NULL
        """, (user_id, guild_id, achievement_type)) as cursor:
            achievements_to_update = await cursor.fetchall()

        unlocked_achievements = []
        for ach in achievements_to_update:
            if achievement_type == 'REACH_LEVEL':
                new_progress = value_to_add
            else:
                new_progress = ach['progress'] + value_to_add

            await db.execute("UPDATE user_achievements SET progress = ? WHERE user_id = ? AND guild_id = ? AND achievement_id = ?", (new_progress, user_id, guild_id, ach['achievement_id']))

            if new_progress >= ach['target_value']:
                now_str = datetime.datetime.now(
                    datetime.timezone.utc).isoformat()
                await db.execute("UPDATE user_achievements SET unlocked_timestamp = ? WHERE user_id = ? AND guild_id = ? AND achievement_id = ?", (now_str, user_id, guild_id, ach['achievement_id']))

                if ach['reward_coin'] > 0:
                    # Truyền kết nối 'db' hiện tại vào hàm con
                    await update_coins(user_id, guild_id, ach['reward_coin'], db_conn=db)
                if ach['reward_xp'] > 0:
                    # Truyền kết nối 'db' hiện tại vào hàm con
                    await update_user_xp(user_id, guild_id, ach['reward_xp'], db_conn=db)

                unlocked_achievements.append(dict(ach))

        await db.commit()  # Commit tất cả thay đổi (cả achievement và rewards) cùng lúc
        return unlocked_achievements


async def get_user_achievements(user_id, guild_id):
    """Lấy danh sách tất cả thành tựu (đã hoàn thành và chưa) của người dùng."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ua.*, a.name, a.description, a.target_value, a.reward_coin, a.reward_xp, a.badge_emoji
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.achievement_id
            WHERE ua.user_id = ? AND ua.guild_id = ?
            ORDER BY ua.unlocked_timestamp DESC, a.name ASC
        """, (user_id, guild_id)) as cursor:
            achievements = await cursor.fetchall()
        return [dict(row) for row in achievements]


async def get_user_completed_achievements(user_id, guild_id):
    """Lấy danh sách emoji và tên của các thành tựu ĐÃ HOÀN THÀNH."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT a.name, a.badge_emoji
            FROM user_achievements ua
            JOIN achievements a ON ua.achievement_id = a.achievement_id
            WHERE ua.user_id = ? AND ua.guild_id = ? AND ua.unlocked_timestamp IS NOT NULL
            AND a.badge_emoji IS NOT NULL
        """, (user_id, guild_id)) as cursor:
            badges = await cursor.fetchall()
        return [dict(row) for row in badges]


async def set_coins(user_id, guild_id, amount):
    """Trực tiếp đặt số coin của người dùng thành một giá trị cụ thể."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO users (user_id, guild_id, coins) VALUES (?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET coins = excluded.coins
        ''', (user_id, guild_id, amount))
        await db.commit()


async def remove_item_from_all_inventories(guild_id, item_id):
    """Xóa một loại vật phẩm nhất định khỏi kho đồ của tất cả mọi người trong server."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM inventory WHERE guild_id = ? AND item_id = ?", (guild_id, item_id))
        await db.commit()


async def get_partner(guild_id, user_id):
    """Tìm bạn đời của một người dùng trong một server cụ thể."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Sửa lỗi: Thêm guild_id vào câu truy vấn và truyền đủ 3 tham số
        query = "SELECT user1_id, user2_id FROM relationships WHERE guild_id = ? AND (user1_id = ? OR user2_id = ?)"
        async with db.execute(query, (guild_id, user_id, user_id)) as cursor:
            relationship = await cursor.fetchone()

        if not relationship:
            return None

        # Trả về ID của người còn lại
        partner_id = relationship['user2_id'] if relationship['user1_id'] == user_id else relationship['user1_id']
        return partner_id


async def create_marriage(guild_id, user1_id, user2_id):
    """Tạo một mối quan hệ hôn nhân."""
    # Sắp xếp để ID nhỏ hơn luôn nằm ở user1_id
    if user1_id > user2_id:
        user1_id, user2_id = user2_id, user1_id

    async with aiosqlite.connect(DB_NAME) as db:
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO relationships (guild_id, user1_id, user2_id, relationship_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (guild_id, user1_id, user2_id, 'MARRIED', now_str)
        )
        await db.commit()


async def delete_marriage(guild_id, user1_id, user2_id):
    """Xóa một mối quan hệ hôn nhân."""
    # Sắp xếp để ID nhỏ hơn luôn nằm ở user1_id
    if user1_id > user2_id:
        user1_id, user2_id = user2_id, user1_id

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "DELETE FROM relationships WHERE guild_id = ? AND user1_id = ? AND user2_id = ?",
            (guild_id, user1_id, user2_id)
        )
        await db.commit()


async def get_boss(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM world_boss WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchone()


async def create_boss(guild_id, name, hp, msg_id, chan_id, spawned_by):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO world_boss (guild_id, boss_name, current_hp, max_hp, message_id, channel_id, spawned_by_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, name, hp, hp, msg_id, chan_id, spawned_by)
        )
        await db.commit()


async def update_boss_hp(guild_id, damage):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE world_boss SET current_hp = current_hp - ? WHERE guild_id = ?", (damage, guild_id))
        await db.commit()


async def delete_boss(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM world_boss WHERE guild_id = ?", (guild_id,))
        await db.commit()


async def get_attacker(guild_id, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM boss_attackers WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)) as cursor:
            return await cursor.fetchone()


async def log_attack(guild_id, user_id, damage):
    async with aiosqlite.connect(DB_NAME) as db:
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO boss_attackers (guild_id, user_id, total_damage, last_attack_timestamp) VALUES (?, ?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET total_damage = total_damage + excluded.total_damage, last_attack_timestamp = excluded.last_attack_timestamp",
            (guild_id, user_id, damage, now_str)
        )
        await db.commit()


async def get_all_attackers(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM boss_attackers WHERE guild_id = ? ORDER BY total_damage DESC", (guild_id,)) as cursor:
            return await cursor.fetchall()


async def clear_attackers(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM boss_attackers WHERE guild_id = ?", (guild_id,))
        await db.commit()


async def add_pinned_message(guild_id, channel_id, author_id, content, embed, last_message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        embed_json = json.dumps(embed.to_dict()) if embed else None
        cursor = await db.execute(
            "INSERT INTO pinned_messages (guild_id, channel_id, author_id, message_content, embed_data, last_message_id) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, author_id, content, embed_json, last_message_id)
        )
        await db.commit()
        return cursor.lastrowid  # Trả về ID của pin mới


async def get_pinned_message(pin_id, guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pinned_messages WHERE pin_id = ? AND guild_id = ?", (pin_id, guild_id)) as cursor:
            return await cursor.fetchone()


async def get_pinned_messages_for_channel(channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pinned_messages WHERE channel_id = ?", (channel_id,)) as cursor:
            return await cursor.fetchall()


async def remove_pinned_message(pin_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM pinned_messages WHERE pin_id = ?", (pin_id,))
        await db.commit()


async def update_last_message_id(pin_id, new_message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE pinned_messages SET last_message_id = ? WHERE pin_id = ?", (new_message_id, pin_id))
        await db.commit()


async def get_all_pinned_messages(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pinned_messages WHERE guild_id = ?", (guild_id,)) as cursor:
            return await cursor.fetchall()


async def add_temp_vc(guild_id, creator_id, channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO temp_voice_channels (guild_id, creator_id, channel_id) VALUES (?, ?, ?)",
            (guild_id, creator_id, channel_id)
        )
        await db.commit()


async def get_temp_vc_by_channel(channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM temp_voice_channels WHERE channel_id = ?", (channel_id,)) as cursor:
            return await cursor.fetchone()


async def remove_temp_vc(channel_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM temp_voice_channels WHERE channel_id = ?", (channel_id,))
        await db.commit()


async def update_perm_damage_bonus(user_id, guild_id, bonus_to_add):
    """Cộng thêm bonus sát thương vĩnh viễn cho người dùng."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET perm_damage_bonus = perm_damage_bonus + ? WHERE user_id = ? AND guild_id = ?", (bonus_to_add, user_id, guild_id))
        await db.commit()


async def get_random_trivia_question():
    """Lấy một câu hỏi đố vui ngẫu nhiên chưa được sử dụng từ DB."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM trivia_questions WHERE is_used = 0") as cursor:
            unused_questions = await cursor.fetchall()

        if not unused_questions:
            await db.execute("UPDATE trivia_questions SET is_used = 0")
            await db.commit()
            print("[Trivia] Tất cả câu hỏi đã được sử dụng. Đang reset lại danh sách.")
            async with db.execute("SELECT * FROM trivia_questions WHERE is_used = 0") as cursor:
                unused_questions = await cursor.fetchall()

        if not unused_questions:
            return None

        chosen_question = random.choice(unused_questions)
        await db.execute("UPDATE trivia_questions SET is_used = 1 WHERE question_id = ?", (chosen_question['question_id'],))
        await db.commit()

        # Giải mã chuỗi JSON từ database thành một list Python
        options_list = json.loads(chosen_question['options'])

        return {
            "text": chosen_question['question_text'],
            "options": options_list,
            "correct": chosen_question['correct_answer'],
            "category": chosen_question['category']
        }
# database.py (thêm vào cuối file)


async def add_active_trivia(message_id, guild_id, channel_id, correct_answer, expiry_timestamp_str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO active_trivia (message_id, guild_id, channel_id, correct_answer, expiry_timestamp) VALUES (?, ?, ?, ?, ?)",
            (message_id, guild_id, channel_id, correct_answer, expiry_timestamp_str)
        )
        await db.commit()


async def get_active_trivia(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM active_trivia WHERE message_id = ?", (message_id,)) as cursor:
            return await cursor.fetchone()


async def update_answered_users(message_id, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT answered_users_json FROM active_trivia WHERE message_id = ?", (message_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return

        users = json.loads(row[0])  # Sửa lại chỉ số [0] để lấy đúng cột
        if user_id not in users:
            users.append(user_id)

        await db.execute("UPDATE active_trivia SET answered_users_json = ? WHERE message_id = ?", (json.dumps(users), message_id))
        await db.commit()


async def get_expired_trivia():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with db.execute("SELECT * FROM active_trivia WHERE expiry_timestamp < ?", (now_str,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]  # Chuyển đổi thành dict


async def remove_active_trivia(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM active_trivia WHERE message_id = ?", (message_id,))
        await db.commit()
