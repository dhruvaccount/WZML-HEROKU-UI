from asyncio import gather, iscoroutinefunction
from html import escape
from re import findall
from time import time

from psutil import cpu_percent, disk_usage, virtual_memory

from ... import (
    DOWNLOAD_DIR,
    bot_cache,
    bot_start_time,
    status_dict,
    task_dict,
    task_dict_lock,
)
from ...core.config_manager import Config
from ..telegram_helper.button_build import ButtonMaker

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class MirrorStatus:
    STATUS_UPLOAD = "Uploading...📤"
    STATUS_DOWNLOAD = "Downloading...📥"
    STATUS_CLONE = "Cloning...♻️"
    STATUS_QUEUEDL = "QueueDl...💤"
    STATUS_QUEUEUP = "QueueUp...💤"
    STATUS_PAUSED = "Paused...⏸️"
    STATUS_ARCHIVE = "Archiving...🔐"
    STATUS_EXTRACT = "Extracting...📂"
    STATUS_SPLIT = "Splitting...✂️"
    STATUS_CHECK = "CheckingUp...📝"
    STATUS_SEED = "Seeding...🌧"    
    STATUS_SAMVID = "Processing SamVid...🎞️"
    STATUS_CONVERT = "Converting...🔄"
    STATUS_FFMPEG = "FFmpeg Processing...🎬"
    STATUS_YT = "YouTube Processing...▶️"
    STATUS_METADATA = "Fetching Metadata...📑" 


class EngineStatus:
    def __init__(self):
        self.STATUS_ARIA2 = f"Aria2 v{bot_cache['eng_versions']['aria2']}"
        self.STATUS_AIOHTTP = f"AioHttp v{bot_cache['eng_versions']['aiohttp']}"
        self.STATUS_GDAPI = f"Google-API v{bot_cache['eng_versions']['gapi']}"
        self.STATUS_QBIT = f"qBit v{bot_cache['eng_versions']['qBittorrent']}"
        self.STATUS_TGRAM = f"Pyro v{bot_cache['eng_versions']['pyrofork']}"
        self.STATUS_MEGA = f"MegaAPI v{bot_cache['eng_versions']['mega']}"
        self.STATUS_YTDLP = f"yt-dlp v{bot_cache['eng_versions']['yt-dlp']}"
        self.STATUS_FFMPEG = f"ffmpeg v{bot_cache['eng_versions']['ffmpeg']}"
        self.STATUS_7Z = f"7z v{bot_cache['eng_versions']['7z']}"
        self.STATUS_RCLONE = f"RClone v{bot_cache['eng_versions']['rclone']}"
        self.STATUS_SABNZBD = f"SABnzbd+ v{bot_cache['eng_versions']['SABnzbd+']}"
        self.STATUS_QUEUE = "QSystem v2"
        self.STATUS_JD = "JDownloader v2"
        self.STATUS_YT = "Youtube-Api"
        self.STATUS_METADATA = "Metadata"


STATUSES = {
    "ALL": "All",
    "DL": MirrorStatus.STATUS_DOWNLOAD,
    "UP": MirrorStatus.STATUS_UPLOAD,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVE,
    "EX": MirrorStatus.STATUS_EXTRACT,
    "SD": MirrorStatus.STATUS_SEED,
    "CL": MirrorStatus.STATUS_CLONE,
    "CM": MirrorStatus.STATUS_CONVERT,
    "SP": MirrorStatus.STATUS_SPLIT,
    "SV": MirrorStatus.STATUS_SAMVID,
    "FF": MirrorStatus.STATUS_FFMPEG,
    "PA": MirrorStatus.STATUS_PAUSED,
    "CK": MirrorStatus.STATUS_CHECK,
}


async def get_task_by_gid(gid: str):
    async with task_dict_lock:
        for tk in task_dict.values():
            if hasattr(tk, "seeding"):
                await tk.update()
            if tk.gid() == gid:
                return tk
        return None


async def get_specific_tasks(status, user_id):
    if status == "All":
        if user_id:
            return [tk for tk in task_dict.values() if tk.listener.user_id == user_id]
        else:
            return list(task_dict.values())
    tasks_to_check = (
        [tk for tk in task_dict.values() if tk.listener.user_id == user_id]
        if user_id
        else list(task_dict.values())
    )
    coro_tasks = []
    coro_tasks.extend(tk for tk in tasks_to_check if iscoroutinefunction(tk.status))
    coro_statuses = await gather(*[tk.status() for tk in coro_tasks])
    result = []
    coro_index = 0
    for tk in tasks_to_check:
        if tk in coro_tasks:
            st = coro_statuses[coro_index]
            coro_index += 1
        else:
            st = tk.status()
        if (st == status) or (
            status == MirrorStatus.STATUS_DOWNLOAD and st not in STATUSES.values()
        ):
            result.append(tk)
    return result


async def get_all_tasks(req_status: str, user_id):
    async with task_dict_lock:
        return await get_specific_tasks(req_status, user_id)


def get_raw_file_size(size):
    num, unit = size.split()
    return int(float(num) * (1024 ** SIZE_UNITS.index(unit)))


def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds: int):
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result


def get_raw_time(time_str: str) -> int:
    time_units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(
        int(value) * time_units[unit]
        for value, unit in findall(r"(\d+)([dhms])", time_str)
    )


def time_to_seconds(time_duration):
    try:
        parts = time_duration.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(float, parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])
        else:
            return 0
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0


def speed_string_to_bytes(size_text: str):
    size = 0
    size_text = size_text.lower()
    if "k" in size_text:
        size += float(size_text.split("k")[0]) * 1024
    elif "m" in size_text:
        size += float(size_text.split("m")[0]) * 1048576
    elif "g" in size_text:
        size += float(size_text.split("g")[0]) * 1073741824
    elif "t" in size_text:
        size += float(size_text.split("t")[0]) * 1099511627776
    elif "b" in size_text:
        size += float(size_text.split("b")[0])
    return size


def get_progress_bar_string(pct):
    pct = float(str(pct).strip("%"))
    p = min(max(pct, 0), 100)
    cFull = int(p // 8)
    p_str = "▰" * cFull
    p_str += "▱" * (12 - cFull)
    return f"[{p_str}]"


async def get_readable_message(sid, is_user, page_no=1, status="All", page_step=1):
    """
    Old-UI styling (BotTheme blocks + header/footer) while keeping all new-UI fields.
    Preserves logic, awaits, pagination, and button callbacks exactly.
    """
    # Old UI header restored
    msg = '<b><a href="https://t.me/DhruvMirrorUpdates"><u>Dhruv Mirror Premium</u></a>\n\n</b>'
    button = None

    # Collect tasks exactly like new UI does
    tasks = await get_specific_tasks(status, sid if is_user else None)

    STATUS_LIMIT = Config.STATUS_LIMIT
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict.setdefault(sid, {})["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict.setdefault(sid, {})["page_no"] = page_no
    start_position = (page_no - 1) * STATUS_LIMIT

    # Build each task block using OLD UI BotTheme keys & order, but include new fields
    for index, task in enumerate(tasks[start_position : STATUS_LIMIT + start_position], start=1):
        # Resolve status (preserve awaits)
        if status != "All":
            tstatus = status
        elif iscoroutinefunction(task.status):
            tstatus = await task.status()
        else:
            tstatus = task.status()

        # Message link logic (same as old)
        msg_link = ""
        try:
            if getattr(task.listener.message, "chat", None) and getattr(task.listener.message.chat, "type", None) in [ChatType.SUPERGROUP, ChatType.CHANNEL] and not Config.DELETE_LINKS:
                msg_link = task.listener.message.link
        except Exception:
            msg_link = ""

        elapsed = time() - task.listener.message.date.timestamp()

        # STATUS_NAME (old UI)
        msg += BotTheme(
            'STATUS_NAME',
            Name="Task is being Processed!" if Config.SAFE_MODE and elapsed >= Config.STATUS_UPDATE_INTERVAL else escape(f"{task.name()}")
        )

        # Progress block for non-seed/split tasks (old UI keys)
        if tstatus not in [MirrorStatus.STATUS_SPLIT, MirrorStatus.STATUS_SEED] and getattr(task.listener, "progress", False):
            msg += BotTheme('BAR', Bar=f"{get_progress_bar_string(task.progress())} {task.progress()}")
            msg += BotTheme('PROCESSED', Processed=f"{task.processed_bytes()} of {task.size()}")
            msg += BotTheme('STATUS', Status=tstatus, Url=msg_link)
            msg += BotTheme('ETA', Eta=task.eta())
            msg += BotTheme('SPEED', Speed=task.speed())
            msg += BotTheme('ELAPSED', Elapsed=get_readable_time(elapsed))
            msg += BotTheme('ENGINE', Engine=getattr(task, 'engine', ''))

            # Preserve old STA_MODE (for templates that expect it) and also include IN/OUT Mode
            # STA_MODE: old behaviour (prefer upload_details['mode'] or listener.mode[0])
            try:
                # Prefer upload_details['mode'] if present (old UI used upload_details['mode'])
                if getattr(task, 'upload_details', None) and isinstance(task.upload_details.get('mode', None), (list, tuple, str)):
                    # If upload_details['mode'] is string/list, provide it
                    ud_mode = task.upload_details.get('mode')
                    msg += BotTheme('STA_MODE', Mode=ud_mode)
                else:
                    # fallback to listener.mode first element
                    lm = task.listener.mode
                    msg += BotTheme('STA_MODE', Mode=lm[0])
            except Exception:
                # fail-safe: skip STA_MODE if unavailable
                pass

            # IN_MODE and OUT_MODE: new UI fields (keep them visible)
            try:
                in_mode, out_mode = task.listener.mode
                msg += BotTheme('IN_MODE', Mode=in_mode)
                msg += BotTheme('OUT_MODE', Mode=out_mode)
            except Exception:
                # if listener.mode not present, try upload_details or skip
                try:
                    ud_mode = task.upload_details.get('mode', None)
                    if isinstance(ud_mode, (list, tuple)) and len(ud_mode) >= 2:
                        msg += BotTheme('IN_MODE', Mode=ud_mode[0])
                        msg += BotTheme('OUT_MODE', Mode=ud_mode[1])
                except Exception:
                    pass

            # Seeders/Leechers if present
            if hasattr(task, 'seeders_num'):
                try:
                    msg += BotTheme('SEEDERS', Seeders=task.seeders_num())
                    msg += BotTheme('LEECHERS', Leechers=task.leechers_num())
                except Exception:
                    pass

        # Seeding block (old UI keys) but keep engine/time/ratio fields
        elif tstatus == MirrorStatus.STATUS_SEED:
            msg += BotTheme('STATUS', Status=tstatus, Url=msg_link)
            msg += BotTheme('SEED_SIZE', Size=task.size())
            try:
                seed_speed_val = task.seed_speed()
            except Exception:
                seed_speed_val = getattr(task, 'upload_speed', lambda: '')()
            msg += BotTheme('SEED_SPEED', Speed=seed_speed_val)
            try:
                msg += BotTheme('UPLOADED', Upload=task.uploaded_bytes())
                msg += BotTheme('RATIO', Ratio=task.ratio())
                msg += BotTheme('TIME', Time=task.seeding_time())
                msg += BotTheme('SEED_ENGINE', Engine=getattr(task, 'engine', ''))
            except Exception:
                pass

            # Also include In/Out mode for seed tasks if available
            try:
                in_mode, out_mode = task.listener.mode
                msg += BotTheme('IN_MODE', Mode=in_mode)
                msg += BotTheme('OUT_MODE', Mode=out_mode)
            except Exception:
                pass

        # Fallback block for split/other tasks (old UI keys) but include IN/OUT if present
        else:
            msg += BotTheme('STATUS', Status=tstatus, Url=msg_link)
            msg += BotTheme('STATUS_SIZE', Size=task.size())
            msg += BotTheme('NON_ENGINE', Engine=getattr(task, 'engine', ''))
            try:
                in_mode, out_mode = task.listener.mode
                msg += BotTheme('IN_MODE', Mode=in_mode)
                msg += BotTheme('OUT_MODE', Mode=out_mode)
            except Exception:
                pass

        # USER and ID (old UI style)
        try:
            msg += BotTheme('USER', User=task.listener.message.from_user.mention(style="html"))
            msg += BotTheme('ID', Id=task.listener.message.from_user.id)
        except Exception:
            msg += BotTheme('USER', User='')
            msg += BotTheme('ID', Id='')

        # qBittorrent select + cancel (same commands)
        if getattr(task, 'engine', '').startswith("qBit"):
            msg += BotTheme('BTSEL', Btsel=f"/{BotCommands.BtSelectCommand}_{task.gid()}")
        msg += BotTheme('CANCEL', Cancel=f"/{BotCommands.CancelMirror}_{task.gid()}")

    # If nothing was appended, preserve original behavior
    if len(msg) == 0:
        return None, None

    # Totals (iterate task_dict like old UI)
    dl_speed = 0
    up_speed = 0

    def _convert_speed(spd):
        try:
            return speed_string_to_bytes(spd)
        except Exception:
            try:
                s = str(spd).upper()
                if 'K' in s:
                    return float(s.split('K')[0]) * 1024
                if 'M' in s:
                    return float(s.split('M')[0]) * 1048576
                if 'G' in s:
                    return float(s.split('G')[0]) * 1073741824
                if 'T' in s:
                    return float(s.split('T')[0]) * 1099511627776
            except Exception:
                return 0
            return 0

    for tk in task_dict.values():
        try:
            tstatus = tk.status() if not iscoroutinefunction(tk.status) else await tk.status()
        except Exception:
            try:
                tstatus = tk.status()
            except Exception:
                tstatus = ""
        spd = tk.speed() if tstatus != MirrorStatus.STATUS_SEED else getattr(tk, 'upload_speed', lambda: '')()
        speed_in_bytes_per_second = _convert_speed(spd)
        if tstatus == MirrorStatus.STATUS_DOWNLOAD:
            dl_speed += speed_in_bytes_per_second
        elif tstatus in [MirrorStatus.STATUS_UPLOAD, MirrorStatus.STATUS_SEED]:
            up_speed += speed_in_bytes_per_second

    # Footer & buttons (old UI)
    msg += BotTheme('FOOTER')
    buttons = ButtonMaker()
    buttons.ibutton(BotTheme('REFRESH', Page=f"{status_dict.get(sid, {}).get('page_no', page_no)}/{pages}"), "status ref")
    if tasks_no > STATUS_LIMIT:
        if Config.BOT_MAX_TASKS:
            msg += BotTheme('BOT_TASKS', Tasks=tasks_no, Ttask=Config.BOT_MAX_TASKS, Free=Config.BOT_MAX_TASKS - tasks_no)
        else:
            msg += BotTheme('TASKS', Tasks=tasks_no)
        buttons = ButtonMaker()
        buttons.ibutton(BotTheme('PREVIOUS'), "status pre")
        buttons.ibutton(BotTheme('REFRESH', Page=f"{status_dict.get(sid, {}).get('page_no', page_no)}/{pages}"), "status ref")
        buttons.ibutton(BotTheme('NEXT'), "status nex")
    button = buttons.build_menu(3)

    # System stats (old UI style)
    msg += BotTheme('Cpu', cpu=cpu_percent())
    msg += BotTheme('FREE', free=get_readable_file_size(disk_usage(DOWNLOAD_DIR).free), free_p=round(100 - disk_usage(DOWNLOAD_DIR).percent, 1))
    msg += BotTheme('Ram', ram=virtual_memory().percent)
    msg += BotTheme('uptime', uptime=get_readable_time(time() - bot_start_time))
    msg += BotTheme('DL', DL=get_readable_file_size(int(dl_speed)))
    msg += BotTheme('UL', UL=get_readable_file_size(int(up_speed)))

    return msg, button
