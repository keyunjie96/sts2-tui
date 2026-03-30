"""Internationalization labels for the TUI.

Game content (card names, enemy names, descriptions, etc.) comes from sts2-cli
already in the correct language.  This module only handles the UI chrome --
labels, banners, and prompts that we render ourselves.

Usage::

    from sts2_tui.tui.i18n import get_label, set_language

    set_language("zh")
    label = get_label("end_turn")  # -> "结束回合"
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Global language setting (module-level singleton)
# ---------------------------------------------------------------------------

_current_lang: str = "en"


def set_language(lang: str) -> None:
    """Set the active display language.  Accepts ``"en"`` or ``"zh"``."""
    global _current_lang
    _current_lang = lang if lang in LABELS else "en"


def get_language() -> str:
    """Return the current display language code."""
    return _current_lang


def get_label(key: str) -> str:
    """Look up a UI label in the current language, falling back to English."""
    return LABELS.get(_current_lang, LABELS["en"]).get(
        key,
        LABELS["en"].get(key, key),
    )


# Convenience alias
L = get_label

# ---------------------------------------------------------------------------
# Label dictionaries
# ---------------------------------------------------------------------------

LABELS: dict[str, dict[str, str]] = {
    "en": {
        # Combat
        "your_turn": ">> YOUR TURN <<",
        "enemy_turn": "-- ENEMY TURN --",
        "energy": "Energy",
        "block": "Block",
        "draw": "Draw",
        "discard": "Discard",
        "exhaust": "Exhaust",
        "hand": "Hand",
        "select_card": "Select card",
        "end_turn": "End Turn",
        "play_card": "Play Card",
        "incoming": "Incoming",
        "damage": "damage",
        "you_have": "You have",
        "need_more_block": "need {0} more Block",
        "fully_blocked": "fully blocked",
        "no_incoming": "No incoming attack damage",
        "defeated": "DEFEATED",
        "target": "TARGET",
        "potions": "Potions",
        "relics": "Relics",
        "potion": "potion",
        "no_potions": "No potions available!",
        "stars": "Stars",
        "fallen": "FALLEN",

        # Turn / act / floor
        "act": "Act",
        "floor": "Floor",
        "turn": "TURN",
        "boss": "Boss",

        # Cards
        "unplayable": "unplayable",
        "cost": "Cost",
        "upgrade": "Upgrade",
        "upgraded": "Upgraded",

        # Card reward
        "card_reward": "CARD REWARD",
        "choose_card_add": "Choose a card to add to your deck",
        "select_first": "Select a card first! Press [1-3]",
        "skip": "Skip",
        "confirm": "Confirm",
        "select": "Select",
        "leave": "Leave",
        "potion_rewards": "POTION REWARDS",
        "potion_slots_full": "Potion belt full!",
        "collect_potion": "Collect",
        "skip_potions": "Skip Potions",
        "discard_for_potion": "Discard & Collect",
        "belt_potion": "Belt",

        # Map
        "map": "MAP",
        "choose_path": "Choose your path",
        "select_path": "Select path",
        "no_paths": "No paths available.",
        "remaining": "Remaining",
        "next": "Next",
        "you_are_here": "YOU ARE HERE",
        "loading_map": "Loading map...",
        "no_map_data": "No map data available.",
        "deck": "Deck",
        "visited": "Visited",

        # Rest site
        "rest_site": "REST SITE",
        "rest": "Rest",
        "smith": "Smith",
        "option": "Option",
        "unavailable": "unavailable",
        "heal_desc": "Heal {0} HP ({1} -> {2})",
        "smith_desc": "Upgrade a card in your deck",
        "lift": "Lift",
        "toke": "Toke",
        "dig": "Dig",
        "recall": "Recall",

        # Event
        "event": "EVENT",
        "choose_option": "Choose an option:",
        "locked": "locked",
        "no_options": "No options available.",

        # Shop
        "shop": "SHOP",
        "cards_for_sale": "CARDS FOR SALE",
        "shop_relics": "RELICS",
        "shop_potions": "POTIONS",
        "services": "SERVICES",
        "remove_card": "Remove a card",
        "remove_card_desc": "Remove a card from your deck",
        "buy": "Buy",
        "not_enough_gold": "Not enough gold! Need {0}g, have {1}g.",
        "select_item_first": "Select an item first!",
        "shop_empty": "The shop is empty.",
        "leave_shop": "Leave Shop",
        "sale": "SALE",

        # Character select
        "sls_cli": "SLS-CLI",
        "terminal_client": "Slay the Spire 2 -- Terminal Client",
        "choose_character": "Choose your character:",
        "start": "Start",
        "quit": "Quit",

        # Generic
        "options": "Options:",
        "proceed": "Proceed",
        "press_enter": "Press Enter to proceed.",
        "navigate": "Navigate",

        # Deck viewer
        "your_deck": "YOUR DECK ({0} cards)",
        "deck_empty": "Your deck is empty.",

        # Combat overlays
        "victory": "VICTORY!",
        "all_enemies_defeated": "All enemies defeated.",
        "continue": "Continue",
        "defeat": "DEFEATED",
        "you_have_been_slain": "You have been slain.",

        # Game over
        "game_over": "GAME OVER",

        # Help
        "keyboard_shortcuts": "Keyboard Shortcuts",
        "combat_controls": "COMBAT CONTROLS",
        "navigation": "NAVIGATION",
        "card": "card",
        "target_label": "target",
        "play": "play",
        "end": "end",
        "help": "help",
        "close": "Close",
        "scroll": "Scroll",
        "use_potion": "Use Potion",
        "view_deck": "View your deck",
        "back_close": "Back / close overlay",
        "quit_game": "Quit game",
        "this_help": "This help screen",

        # Global help overlay (context-aware)
        "general_controls": "GENERAL CONTROLS",
        "screen_controls": "SCREEN CONTROLS",
        "help_view_deck": "[D]       View your deck",
        "help_view_relics": "[R]       View relics & potions",
        "help_quit": "[Q]       Quit game",
        "help_esc": "[Esc]     Back / close overlay",
        "help_help": "[?/F1]    This help screen",

        # Screen transition feedback
        "transition_combat_victory": "Combat Victory!",
        "transition_entered_map": "Returned to Map",
        "transition_card_reward": "Choose a Card Reward",
        "transition_rest_site": "Entered Rest Site",
        "transition_event": "Entered Event",
        "transition_shop": "Entered Shop",
        "transition_game_over_victory": "Victory! Run Complete!",
        "transition_game_over_defeat": "You have been defeated...",

        # Error recovery
        "error_occurred": "ERROR",
        "error_retry": "Retry",
        "error_go_map": "Go to Map",
        "error_quit": "Quit Game",
        "error_message": "Something went wrong",

        # Pile viewers
        "draw_pile": "Draw Pile",
        "discard_pile": "Discard Pile",
        "exhaust_pile": "Exhaust Pile",

        # Potion menu
        "potion_menu_title": "POTIONS",
        "potion_discard_mode": "DISCARD",
        "potion_select_target": "Select Target",
        "potion_targeted": "targeted",
        "potion_aoe": "All Enemies",
        "potion_empty": "empty",
        "potion_empty_slot": "That slot is empty!",
        "potion_no_targets": "No targets available!",
        "potion_next_target": "Next target",
        "potion_cancel": "Cancel",
        "potion_use": "Use",
        "potion_discard_label": "Discard",
        "potion_discard_slot": "Discard slot",

        # Card select constraints
        "select_exactly": "Select exactly {0} card{1}",
        "select_range": "Select {0}-{1} cards",
        "select_up_to": "Select up to {0} card{1}",
        "select_at_least": "Select at least {0} card{1}",

        # Status bar
        "hp_label": "HP",
        "gold_label": "Gold",
    },
    "zh": {
        # Combat
        "your_turn": ">> 你的回合 <<",
        "enemy_turn": "-- 敌方回合 --",
        "energy": "能量",
        "block": "格挡",
        "draw": "抽牌堆",
        "discard": "弃牌堆",
        "exhaust": "消耗堆",
        "hand": "手牌",
        "select_card": "选择卡牌",
        "end_turn": "结束回合",
        "play_card": "出牌",
        "incoming": "即将受到",
        "damage": "伤害",
        "you_have": "你拥有",
        "need_more_block": "还需要 {0} 格挡",
        "fully_blocked": "完全格挡",
        "no_incoming": "没有即将到来的攻击伤害",
        "defeated": "已击败",
        "target": "目标",
        "potions": "药水",
        "relics": "遗物",
        "potion": "药水",
        "no_potions": "没有可用的药水！",
        "stars": "星辰",
        "fallen": "已阵亡",

        # Turn / act / floor
        "act": "幕",
        "floor": "层",
        "turn": "回合",
        "boss": "首领",

        # Cards
        "unplayable": "无法使用",
        "cost": "费用",
        "upgrade": "升级",
        "upgraded": "已升级",

        # Card reward
        "card_reward": "卡牌奖励",
        "choose_card_add": "选择一张卡牌加入你的牌组",
        "select_first": "请先选择一张卡牌！按 [1-3]",
        "skip": "跳过",
        "confirm": "确认",
        "select": "选择",
        "leave": "离开",
        "potion_rewards": "药水奖励",
        "potion_slots_full": "药水栏已满！",
        "collect_potion": "拾取",
        "skip_potions": "跳过药水",
        "discard_for_potion": "丢弃并拾取",
        "belt_potion": "药水栏",

        # Map
        "map": "地图",
        "choose_path": "选择你的路径",
        "select_path": "选择路径",
        "no_paths": "没有可用的路径。",
        "remaining": "剩余",
        "next": "下一个",
        "you_are_here": "你在这里",
        "loading_map": "加载地图...",
        "no_map_data": "没有地图数据。",
        "deck": "牌组",
        "visited": "已访问",

        # Rest site
        "rest_site": "篝火",
        "rest": "休息",
        "smith": "锻造",
        "option": "选项",
        "unavailable": "不可用",
        "heal_desc": "恢复 {0} 生命 ({1} -> {2})",
        "smith_desc": "升级牌组中的一张卡牌",
        "lift": "锻炼",
        "toke": "吞吐",
        "dig": "挖掘",
        "recall": "回忆",

        # Event
        "event": "事件",
        "choose_option": "选择一个选项：",
        "locked": "已锁定",
        "no_options": "没有可用的选项。",

        # Shop
        "shop": "商店",
        "cards_for_sale": "卡牌出售",
        "shop_relics": "遗物",
        "shop_potions": "药水",
        "services": "服务",
        "remove_card": "移除卡牌",
        "remove_card_desc": "从牌组中移除一张卡牌",
        "buy": "购买",
        "not_enough_gold": "金币不足！需要 {0}，拥有 {1}。",
        "select_item_first": "请先选择一件物品！",
        "shop_empty": "商店是空的。",
        "leave_shop": "离开商店",
        "sale": "特价",

        # Character select
        "sls_cli": "SLS-CLI",
        "terminal_client": "尖塔奇兵 2 -- 终端客户端",
        "choose_character": "选择你的角色：",
        "start": "开始",
        "quit": "退出",

        # Generic
        "options": "选项：",
        "proceed": "继续",
        "press_enter": "按回车键继续。",
        "navigate": "导航",

        # Deck viewer
        "your_deck": "你的牌组（{0} 张卡牌）",
        "deck_empty": "你的牌组是空的。",

        # Combat overlays
        "victory": "胜利！",
        "all_enemies_defeated": "所有敌人已被击败。",
        "continue": "继续",
        "defeat": "战败",
        "you_have_been_slain": "你已被击败。",

        # Game over
        "game_over": "游戏结束",

        # Help
        "keyboard_shortcuts": "快捷键",
        "combat_controls": "战斗控制",
        "navigation": "导航",
        "card": "卡牌",
        "target_label": "目标",
        "play": "出牌",
        "end": "结束",
        "help": "帮助",
        "close": "关闭",
        "scroll": "滚动",
        "use_potion": "使用药水",
        "view_deck": "查看牌组",
        "back_close": "返回 / 关闭",
        "quit_game": "退出游戏",
        "this_help": "帮助界面",

        # Global help overlay (context-aware)
        "general_controls": "通用控制",
        "screen_controls": "当前界面控制",
        "help_view_deck": "[D]       查看牌组",
        "help_view_relics": "[R]       查看遗物和药水",
        "help_quit": "[Q]       退出游戏",
        "help_esc": "[Esc]     返回 / 关闭",
        "help_help": "[?/F1]    帮助界面",

        # Screen transition feedback
        "transition_combat_victory": "战斗胜利！",
        "transition_entered_map": "返回地图",
        "transition_card_reward": "选择卡牌奖励",
        "transition_rest_site": "进入篝火",
        "transition_event": "进入事件",
        "transition_shop": "进入商店",
        "transition_game_over_victory": "胜利！通关！",
        "transition_game_over_defeat": "你被击败了...",

        # Error recovery
        "error_occurred": "错误",
        "error_retry": "重试",
        "error_go_map": "返回地图",
        "error_quit": "退出游戏",
        "error_message": "发生了错误",

        # Pile viewers
        "draw_pile": "抽牌堆",
        "discard_pile": "弃牌堆",
        "exhaust_pile": "消耗堆",

        # Potion menu
        "potion_menu_title": "药水",
        "potion_discard_mode": "丢弃",
        "potion_select_target": "选择目标",
        "potion_targeted": "需选目标",
        "potion_aoe": "全体敌人",
        "potion_empty": "空",
        "potion_empty_slot": "该槽位是空的！",
        "potion_no_targets": "没有可选目标！",
        "potion_next_target": "下一个目标",
        "potion_cancel": "取消",
        "potion_use": "使用",
        "potion_discard_label": "丢弃",
        "potion_discard_slot": "丢弃槽位",

        # Card select constraints
        "select_exactly": "恰好选择 {0} 张卡牌",
        "select_range": "选择 {0}-{1} 张卡牌",
        "select_up_to": "最多选择 {0} 张卡牌",
        "select_at_least": "至少选择 {0} 张卡牌",

        # Status bar
        "hp_label": "生命",
        "gold_label": "金币",
    },
}
