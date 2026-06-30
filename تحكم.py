#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

# ================== الإعدادات ==================
TOKEN = '8991924077:AAEuzyd1BCz988_bwVwhovnHfw2kADhFlrs'
ADMIN_ID = 8343786519

# حالات المحادثة
WAITING_COMMAND, WAITING_CD, WAITING_UPLOAD_PATH, WAITING_DOWNLOAD_PATH, WAITING_KILL_PID, WAITING_BACKUP_PATH = range(6)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================== دوال مساعدة ==================
async def check_auth(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

def split_text_smart(text: str, max_len: int = 4096) -> list:
    if len(text) <= max_len:
        return [text]
    parts = []
    lines = text.splitlines(keepends=True)
    current = ""
    for line in lines:
        if len(current) + len(line) <= max_len:
            current += line
        else:
            if current:
                parts.append(current.rstrip('\n'))
            if len(line) > max_len:
                for i in range(0, len(line), max_len):
                    parts.append(line[i:i+max_len])
                current = ""
            else:
                current = line
    if current:
        parts.append(current.rstrip('\n'))
    return parts

async def run_shell_command(cmd: str, cwd: str = None, timeout: int = 120) -> dict:
    try:
        if cwd and not os.path.isdir(cwd):
            cwd = os.getcwd()
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            shell=True,
            executable='/bin/bash'
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return {
            'stdout': stdout.decode('utf-8', errors='replace'),
            'stderr': stderr.decode('utf-8', errors='replace'),
            'returncode': process.returncode,
        }
    except asyncio.TimeoutError:
        try:
            process.kill()
        except:
            pass
        return {'stdout': '', 'stderr': f'⚠️ انتهى الوقت المحدد ({timeout} ثانية)', 'returncode': -1}
    except Exception as e:
        return {'stdout': '', 'stderr': f'❌ خطأ في التنفيذ: {e}', 'returncode': -1}

def get_size_str(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

# ================== دالة معلومات النظام المحسنة ==================
async def get_system_info() -> str:
    info_lines = []
    # وقت التشغيل
    try:
        uptime_seconds = (datetime.now() - datetime.fromtimestamp(psutil.boot_time())).total_seconds()
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{int(days)}d {int(hours)}h {int(minutes)}m {int(seconds)}s"
        info_lines.append(f"⏱ **وقت التشغيل:** {uptime_str}")
    except Exception:
        try:
            result = await run_shell_command('uptime -p', timeout=5)
            if result['returncode'] == 0:
                uptime_str = result['stdout'].strip()
                info_lines.append(f"⏱ **وقت التشغيل:** {uptime_str}")
            else:
                info_lines.append("⏱ **وقت التشغيل:** غير متاح")
        except:
            info_lines.append("⏱ **وقت التشغيل:** غير متاح")

    # CPU
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        info_lines.append(f"💻 **المعالج:** {cpu_count} نواة منطقية")
        info_lines.append(f"📈 **استخدام CPU:** {cpu_percent}%")
    except Exception:
        try:
            result = await run_shell_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1", timeout=5)
            if result['returncode'] == 0 and result['stdout'].strip():
                cpu = result['stdout'].strip()
                info_lines.append(f"📈 **استخدام CPU:** {cpu}%")
            else:
                info_lines.append("📈 **استخدام CPU:** غير متاح")
        except:
            info_lines.append("📈 **استخدام CPU:** غير متاح")
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cores = sum(1 for line in f if line.startswith('processor'))
            info_lines.append(f"💻 **المعالج:** {cores} نواة منطقية")
        except:
            pass

    # الذاكرة
    try:
        mem = psutil.virtual_memory()
        info_lines.append(f"🧠 **الذاكرة:**")
        info_lines.append(f"   - الإجمالي: {get_size_str(mem.total)}")
        info_lines.append(f"   - المستخدم: {get_size_str(mem.used)}")
        info_lines.append(f"   - المتاح: {get_size_str(mem.available)}")
    except Exception:
        try:
            result = await run_shell_command("free -m", timeout=5)
            if result['returncode'] == 0:
                lines = result['stdout'].splitlines()
                for line in lines:
                    if 'Mem:' in line:
                        parts = line.split()
                        total = int(parts[1])
                        used = int(parts[2])
                        avail = int(parts[6]) if len(parts) > 6 else total - used
                        info_lines.append(f"🧠 **الذاكرة:**")
                        info_lines.append(f"   - الإجمالي: {total} MB")
                        info_lines.append(f"   - المستخدم: {used} MB")
                        info_lines.append(f"   - المتاح: {avail} MB")
                        break
            else:
                info_lines.append("🧠 **الذاكرة:** غير متاح")
        except:
            info_lines.append("🧠 **الذاكرة:** غير متاح")

    # المساحة
    try:
        disk = psutil.disk_usage('/')
        info_lines.append(f"💾 **المساحة (`/`):**")
        info_lines.append(f"   - الإجمالي: {get_size_str(disk.total)}")
        info_lines.append(f"   - المستخدم: {get_size_str(disk.used)}")
        info_lines.append(f"   - المتاح: {get_size_str(disk.free)}")
    except Exception:
        try:
            result = await run_shell_command("df -h /", timeout=5)
            if result['returncode'] == 0:
                lines = result['stdout'].splitlines()
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        info_lines.append(f"💾 **المساحة (`/`):**")
                        info_lines.append(f"   - الإجمالي: {parts[1]}")
                        info_lines.append(f"   - المستخدم: {parts[2]}")
                        info_lines.append(f"   - المتاح: {parts[3]}")
                    else:
                        info_lines.append("💾 **المساحة:** غير متاح")
            else:
                info_lines.append("💾 **المساحة:** غير متاح")
        except:
            info_lines.append("💾 **المساحة:** غير متاح")

    header = "🖥️ **معلومات النظام**\n──────────────────\n"
    return header + "\n".join(info_lines)

# ================== دالة النسخ الاحتياطي ==================
async def create_backup(path: str, speed_limit: str = "1m") -> dict:
    """
    ضغط المجلد المحدد إلى ملف tar.gz مع تحديد السرعة باستخدام pv إذا كان موجوداً.
    تعيد مسار الملف المضغوط وحالة النجاح.
    """
    # التحقق من وجود pv
    pv_check = await run_shell_command("which pv", timeout=5)
    has_pv = pv_check['returncode'] == 0 and pv_check['stdout'].strip() != ""

    # إنشاء ملف مؤقت
    fd, temp_path = tempfile.mkstemp(suffix=".tar.gz", prefix="backup_")
    os.close(fd)

    # تحديد أمر الضغط
    if has_pv:
        cmd = f"tar -czf - -C {path} . | pv -L {speed_limit} > {temp_path}"
    else:
        cmd = f"tar -czf {temp_path} -C {path} ."
        # إذا لم يكن pv موجوداً، نعطي تحذيراً في المخرجات

    result = await run_shell_command(cmd, timeout=3600)  # مهلة ساعة للضغط الكبير
    if result['returncode'] != 0:
        # حذف الملف المؤقت في حال الفشل
        try:
            os.unlink(temp_path)
        except:
            pass
        return {'success': False, 'error': result['stderr'], 'path': None}

    # التحقق من أن الملف موجود وليس فارغاً
    if os.path.getsize(temp_path) == 0:
        os.unlink(temp_path)
        return {'success': False, 'error': "الملف المضغوط فارغ.", 'path': None}

    return {'success': True, 'path': temp_path, 'has_pv': has_pv}

# ================== القوائم ==================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    keyboard = [
        [InlineKeyboardButton("📂 إدارة الملفات", callback_data='files_menu')],
        [InlineKeyboardButton("⚙️ تنفيذ أمر", callback_data='exec_cmd')],
        [InlineKeyboardButton("📊 معلومات النظام", callback_data='sysinfo')],
        [InlineKeyboardButton("🛑 إدارة العمليات", callback_data='process_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👋 أهلاً بك في لوحة التحكم الكاملة للسيرفر\nاختر ما تريد:"
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def files_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📋 عرض الملفات (ls)", callback_data='ls')],
        [InlineKeyboardButton("📁 تغيير المجلد (cd)", callback_data='cd')],
        [InlineKeyboardButton("📦 نسخ احتياطي للمجلد الحالي", callback_data='backup')],
        [InlineKeyboardButton("⬆️ رفع ملف", callback_data='upload')],
        [InlineKeyboardButton("⬇️ تحميل ملف", callback_data='download')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='main_menu')],
    ]
    await query.edit_message_text("📂 **إدارة الملفات**\nاختر إجراء:", reply_markup=InlineKeyboardMarkup(keyboard))

async def process_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📋 عرض العمليات", callback_data='ps')],
        [InlineKeyboardButton("❌ إنهاء عملية", callback_data='kill')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='main_menu')],
    ]
    await query.edit_message_text("🛑 **إدارة العمليات**\nاختر إجراء:", reply_markup=InlineKeyboardMarkup(keyboard))

# ================== أوامر البوت الأساسية ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return
    if 'cwd' not in context.user_data:
        context.user_data['cwd'] = os.getcwd()
    await main_menu(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    help_text = (
        "📖 **الأوامر المتاحة:**\n"
        "/start - عرض القائمة الرئيسية\n"
        "/help - عرض هذه المساعدة\n"
        "/exec <أمر> - تنفيذ أمر مباشر (مثال: /exec ls -la)\n"
        "/ls - عرض الملفات في المجلد الحالي\n"
        "/cd <مسار> - تغيير المجلد\n"
        "/sysinfo - عرض معلومات النظام\n"
        "/ps - عرض العمليات\n"
        "/kill <PID> - إنهاء عملية\n"
        "/upload - رفع ملف (ستتبع الخطوات)\n"
        "/download <مسار> - تحميل ملف\n"
        "/backup <مسار> - عمل نسخ احتياطي للمجلد (ضغط وإرسال)\n"
        "/cancel - إلغاء العملية الحالية\n\n"
        "يمكنك أيضاً كتابة الأمر مباشرة في الشات (بدون /) لتنفيذه."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    context.user_data.pop('command_state', None)
    context.user_data.pop('upload_target', None)
    await update.message.reply_text("❌ تم إلغاء العملية الحالية.", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')
    ]]))

# ================== معالجة الأزرار ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'main_menu':
        await main_menu(update, context, edit=True)
        return

    if data == 'files_menu':
        await files_menu(update, context)
        return

    if data == 'process_menu':
        await process_menu(update, context)
        return

    # ls
    if data == 'ls':
        cwd = context.user_data.get('cwd', os.getcwd())
        try:
            result = await run_shell_command('ls -la --color=never --group-directories-first', cwd=cwd)
            output = result['stdout'] or result['stderr']
            if not output:
                output = "📭 المجلد فارغ"
            header = f"📂 **المجلد الحالي:** `{cwd}`\n\n"
            full_text = header + output
            parts = split_text_smart(full_text)
            for i, part in enumerate(parts):
                if i == 0:
                    await query.message.reply_text(part, parse_mode='Markdown')
                else:
                    await query.message.reply_text(part)
            await query.delete_message()
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}")
        return

    # cd
    if data == 'cd':
        await query.edit_message_text(
            "📁 **تغيير المجلد**\nأرسل المسار الجديد (مثل `/home` أو `..`):",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['command_state'] = 'cd'
        return

    # backup - طلب مسار المجلد المراد نسخه احتياطياً
    if data == 'backup':
        cwd = context.user_data.get('cwd', os.getcwd())
        await query.edit_message_text(
            f"📦 **نسخ احتياطي للمجلد الحالي:** `{cwd}`\n"
            "هل تريد استخدام هذا المجلد؟\n"
            "أرسل `نعم` أو اكتب مساراً آخر.\n"
            "(يمكنك أيضاً استخدام الأمر `/backup <مسار>` مباشرة)",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['command_state'] = 'backup_path'
        return

    # upload
    if data == 'upload':
        await query.edit_message_text(
            "⬆️ **رفع ملف**\nأرسل المسار الذي تريد حفظ الملف فيه (مثال: `/home/user/file.txt`):",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['command_state'] = 'upload_path'
        return

    # download
    if data == 'download':
        await query.edit_message_text(
            "⬇️ **تحميل ملف**\nأرسل المسار الكامل للملف الذي تريد تحميله (مثال: `/home/user/file.txt`):",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['command_state'] = 'download_path'
        return

    # exec
    if data == 'exec_cmd':
        await query.edit_message_text(
            "⚙️ **تنفيذ أمر**\nاكتب الأمر الذي تريد تنفيذه (مثل `ls -la`):",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['command_state'] = 'exec'
        return

    # sysinfo
    if data == 'sysinfo':
        await query.edit_message_text("⏳ جلب معلومات النظام...")
        info = await get_system_info()
        parts = split_text_smart(info)
        for i, part in enumerate(parts):
            if i == 0:
                await query.edit_message_text(part, parse_mode='Markdown')
            else:
                await query.message.reply_text(part)
        return

    # ps
    if data == 'ps':
        await query.edit_message_text("⏳ جلب قائمة العمليات...")
        try:
            result = await run_shell_command('ps aux --sort=-%mem | head -30', timeout=10)
            output = result['stdout'] or result['stderr']
            if not output:
                output = "لا توجد عمليات."
            output = f"📋 **أكثر 30 عملية استهلاكاً للذاكرة**\n\n```\n{output}\n```"
            parts = split_text_smart(output)
            for i, part in enumerate(parts):
                if i == 0:
                    await query.message.reply_text(part, parse_mode='Markdown')
                else:
                    await query.message.reply_text(part)
            await query.delete_message()
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {e}")
        return

    # kill
    if data == 'kill':
        await query.edit_message_text(
            "❌ **إنهاء عملية**\nأرسل رقم PID للعملية التي تريد إنهاءها:",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['command_state'] = 'kill'
        return

# ================== معالجة الرسائل النصية ==================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        await update.message.reply_text("⛔ غير مصرح.")
        return

    state = context.user_data.get('command_state')
    text = update.message.text

    if state:
        cwd = context.user_data.get('cwd', os.getcwd())

        if state == 'cd':
            new_path = os.path.abspath(os.path.join(cwd, text))
            if os.path.isdir(new_path):
                context.user_data['cwd'] = new_path
                await update.message.reply_text(f"✅ تم تغيير المجلد إلى: `{new_path}`", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ المسار غير صحيح أو غير موجود: `{text}`", parse_mode='Markdown')
            context.user_data.pop('command_state', None)
            await main_menu(update, context)
            return

        if state == 'exec':
            await update.message.reply_text(f"⏳ جاري تنفيذ: `{text}`", parse_mode='Markdown')
            result = await run_shell_command(text, cwd=cwd)
            output = result['stdout'] or result['stderr'] or "✅ تم التنفيذ (لا يوجد مخرجات)."
            if result['returncode'] != 0:
                output = f"⚠️ رمز الخطأ: {result['returncode']}\n\n{output}"
            parts = split_text_smart(output)
            for part in parts:
                await update.message.reply_text(f"```\n{part}\n```", parse_mode='Markdown')
            context.user_data.pop('command_state', None)
            await main_menu(update, context)
            return

        if state == 'backup_path':
            # تحديد المسار: إذا كتب "نعم" أو ترك فارغاً نستخدم المسار الحالي
            if text.lower() in ['نعم', 'yes', 'y', '']:
                path_to_backup = cwd
            else:
                # حاول تحويل النص إلى مسار مطلق
                path_to_backup = os.path.abspath(os.path.join(cwd, text))
                if not os.path.isdir(path_to_backup):
                    await update.message.reply_text(f"❌ المسار غير صحيح أو غير موجود: `{text}`", parse_mode='Markdown')
                    context.user_data.pop('command_state', None)
                    await main_menu(update, context)
                    return

            await update.message.reply_text(f"⏳ جاري ضغط المجلد: `{path_to_backup}` ... قد يستغرق وقتاً حسب حجم الملفات.", parse_mode='Markdown')
            # تنفيذ الضغط
            backup_result = await create_backup(path_to_backup, speed_limit="1m")
            if not backup_result['success']:
                await update.message.reply_text(f"❌ فشل إنشاء النسخ الاحتياطي: {backup_result['error']}")
            else:
                file_path = backup_result['path']
                has_pv = backup_result['has_pv']
                caption = f"✅ تم إنشاء نسخ احتياطي للمجلد `{path_to_backup}`\n"
                if has_pv:
                    caption += "🚀 تم تحديد سرعة النقل بـ 1 ميجابايت/ثانية."
                else:
                    caption += "⚠️ **ملاحظة:** `pv` غير مثبت، تم الضغط والإرسال بدون تحديد سرعة (قد يستهلك نطاقاً عالياً)."
                try:
                    # إرسال الملف
                    with open(file_path, 'rb') as f:
                        await update.message.reply_document(
                            document=f,
                            filename=os.path.basename(file_path),
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    # حذف الملف المؤقت بعد الإرسال
                    os.unlink(file_path)
                except Exception as e:
                    await update.message.reply_text(f"❌ فشل إرسال الملف: {e}")
                    try:
                        os.unlink(file_path)
                    except:
                        pass
            context.user_data.pop('command_state', None)
            await main_menu(update, context)
            return

        if state == 'upload_path':
            context.user_data['upload_target'] = text
            await update.message.reply_text(
                f"📤 الآن أرسل الملف (صورة، وثيقة، إلخ) ليتم رفعه إلى:\n`{text}`",
                parse_mode='Markdown'
            )
            context.user_data['command_state'] = 'upload_waiting'
            return

        if state == 'download_path':
            file_path = os.path.abspath(os.path.join(cwd, text))
            if os.path.isfile(file_path):
                try:
                    await update.message.reply_document(
                        document=open(file_path, 'rb'),
                        filename=os.path.basename(file_path),
                        caption=f"✅ تم تحميل الملف: `{file_path}`",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    await update.message.reply_text(f"❌ فشل التحميل: {e}")
            else:
                await update.message.reply_text(f"❌ الملف غير موجود: `{text}`", parse_mode='Markdown')
            context.user_data.pop('command_state', None)
            await main_menu(update, context)
            return

        if state == 'kill':
            try:
                pid = int(text)
                process = psutil.Process(pid)
                process.terminate()
                await update.message.reply_text(f"✅ تم إرسال إشارة إنهاء للعملية {pid} ({process.name()})")
            except psutil.NoSuchProcess:
                await update.message.reply_text(f"❌ لا توجد عملية بالـ PID: {pid}")
            except psutil.AccessDenied:
                await update.message.reply_text(f"⛔ صلاحيات غير كافية لإنهاء العملية {pid}")
            except ValueError:
                await update.message.reply_text("❌ يجب إدخال رقم صحيح (PID).")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop('command_state', None)
            await main_menu(update, context)
            return

        # حالة غير معروفة
        context.user_data.pop('command_state', None)
        await update.message.reply_text("⚠️ حدث خطأ في الحالة. الرجاء استخدام /start من جديد.")
        return

    # إذا لم توجد حالة وبدأ النص بـ '/' يتم تجاهله (CommandHandler يعالجها)
    if text.startswith('/'):
        return

    # تنفيذ الأمر مباشرة (بدون /)
    cwd = context.user_data.get('cwd', os.getcwd())
    await update.message.reply_text(f"⏳ جاري تنفيذ: `{text}`", parse_mode='Markdown')
    result = await run_shell_command(text, cwd=cwd)
    output = result['stdout'] or result['stderr'] or "✅ تم التنفيذ (لا يوجد مخرجات)."
    if result['returncode'] != 0:
        output = f"⚠️ رمز الخطأ: {result['returncode']}\n\n{output}"
    parts = split_text_smart(output)
    for part in parts:
        await update.message.reply_text(f"```\n{part}\n```", parse_mode='Markdown')

# ================== معالجة رفع الملفات ==================
async def file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    state = context.user_data.get('command_state')
    if state != 'upload_waiting':
        await update.message.reply_text("⚠️ لم تطلب رفع ملف. استخدم الزر أولاً.")
        return

    target_path = context.user_data.get('upload_target')
    if not target_path:
        await update.message.reply_text("❌ حدث خطأ: المسار غير معروف.")
        context.user_data.pop('command_state', None)
        return

    document = update.message.document
    if not document:
        await update.message.reply_text("❌ الرجاء إرسال ملف (وثيقة).")
        return

    file = await document.get_file()
    if target_path.endswith('/') or os.path.isdir(target_path):
        os.makedirs(target_path, exist_ok=True)
        save_path = os.path.join(target_path, document.file_name)
    else:
        dirname = os.path.dirname(target_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        save_path = target_path

    try:
        await file.download_to_drive(save_path)
        await update.message.reply_text(f"✅ تم رفع الملف بنجاح إلى:\n`{save_path}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الرفع: {e}")

    context.user_data.pop('command_state', None)
    context.user_data.pop('upload_target', None)
    await main_menu(update, context)

# ================== أوامر مباشرة (بدون أزرار) ==================
async def exec_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ الرجاء كتابة الأمر بعد /exec، مثال: /exec ls -la")
        return
    cmd = ' '.join(context.args)
    cwd = context.user_data.get('cwd', os.getcwd())
    await update.message.reply_text(f"⏳ جاري تنفيذ: `{cmd}`", parse_mode='Markdown')
    result = await run_shell_command(cmd, cwd=cwd)
    output = result['stdout'] or result['stderr'] or "✅ تم التنفيذ (لا يوجد مخرجات)."
    if result['returncode'] != 0:
        output = f"⚠️ رمز الخطأ: {result['returncode']}\n\n{output}"
    parts = split_text_smart(output)
    for part in parts:
        await update.message.reply_text(f"```\n{part}\n```", parse_mode='Markdown')

async def ls_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    cwd = context.user_data.get('cwd', os.getcwd())
    try:
        result = await run_shell_command('ls -la --color=never --group-directories-first', cwd=cwd)
        output = result['stdout'] or result['stderr']
        if not output:
            output = "📭 المجلد فارغ"
        header = f"📂 **المجلد الحالي:** `{cwd}`\n\n"
        full_text = header + output
        parts = split_text_smart(full_text)
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, parse_mode='Markdown')
            else:
                await update.message.reply_text(part)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def cd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ الرجاء كتابة المسار بعد /cd، مثال: /cd /home")
        return
    new_path = os.path.abspath(os.path.join(context.user_data.get('cwd', os.getcwd()), context.args[0]))
    if os.path.isdir(new_path):
        context.user_data['cwd'] = new_path
        await update.message.reply_text(f"✅ تم تغيير المجلد إلى: `{new_path}`", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ المسار غير صحيح أو غير موجود: `{context.args[0]}`", parse_mode='Markdown')

async def sysinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text("⏳ جلب معلومات النظام...")
    info = await get_system_info()
    parts = split_text_smart(info)
    for i, part in enumerate(parts):
        if i == 0:
            await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(part)

async def ps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    try:
        result = await run_shell_command('ps aux --sort=-%mem | head -30', timeout=10)
        output = result['stdout'] or result['stderr']
        if not output:
            output = "لا توجد عمليات."
        output = f"📋 **أكثر 30 عملية استهلاكاً للذاكرة**\n\n```\n{output}\n```"
        parts = split_text_smart(output)
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, parse_mode='Markdown')
            else:
                await update.message.reply_text(part)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ الرجاء كتابة PID بعد /kill، مثال: /kill 1234")
        return
    try:
        pid = int(context.args[0])
        process = psutil.Process(pid)
        process.terminate()
        await update.message.reply_text(f"✅ تم إرسال إشارة إنهاء للعملية {pid} ({process.name()})")
    except psutil.NoSuchProcess:
        await update.message.reply_text(f"❌ لا توجد عملية بالـ PID: {pid}")
    except psutil.AccessDenied:
        await update.message.reply_text(f"⛔ صلاحيات غير كافية لإنهاء العملية {pid}")
    except ValueError:
        await update.message.reply_text("❌ يجب إدخال رقم صحيح (PID).")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    await update.message.reply_text(
        "⬆️ **رفع ملف**\nأرسل المسار الذي تريد حفظ الملف فيه (مثال: `/home/user/file.txt`):",
        reply_markup=ForceReply(selective=True)
    )
    context.user_data['command_state'] = 'upload_path'

async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ الرجاء كتابة المسار بعد /download، مثال: /download /home/user/file.txt")
        return
    file_path = os.path.abspath(os.path.join(context.user_data.get('cwd', os.getcwd()), context.args[0]))
    if os.path.isfile(file_path):
        try:
            await update.message.reply_document(
                document=open(file_path, 'rb'),
                filename=os.path.basename(file_path),
                caption=f"✅ تم تحميل الملف: `{file_path}`",
                parse_mode='Markdown'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ فشل التحميل: {e}")
    else:
        await update.message.reply_text(f"❌ الملف غير موجود: `{context.args[0]}`", parse_mode='Markdown')

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /backup <مسار> لعمل نسخ احتياطي لمجلد معين"""
    if not await check_auth(update):
        return
    cwd = context.user_data.get('cwd', os.getcwd())
    if not context.args:
        # إذا لم يحدد مساراً، نستخدم المجلد الحالي
        path_to_backup = cwd
    else:
        path_to_backup = os.path.abspath(os.path.join(cwd, context.args[0]))
        if not os.path.isdir(path_to_backup):
            await update.message.reply_text(f"❌ المسار غير صحيح أو غير موجود: `{context.args[0]}`", parse_mode='Markdown')
            return

    await update.message.reply_text(f"⏳ جاري ضغط المجلد: `{path_to_backup}` ... قد يستغرق وقتاً.", parse_mode='Markdown')
    backup_result = await create_backup(path_to_backup, speed_limit="1m")
    if not backup_result['success']:
        await update.message.reply_text(f"❌ فشل إنشاء النسخ الاحتياطي: {backup_result['error']}")
        return

    file_path = backup_result['path']
    has_pv = backup_result['has_pv']
    caption = f"✅ تم إنشاء نسخ احتياطي للمجلد `{path_to_backup}`\n"
    if has_pv:
        caption += "🚀 تم تحديد سرعة النقل بـ 1 ميجابايت/ثانية."
    else:
        caption += "⚠️ **ملاحظة:** `pv` غير مثبت، تم الضغط والإرسال بدون تحديد سرعة (قد يستهلك نطاقاً عالياً)."
    try:
        with open(file_path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(file_path),
                caption=caption,
                parse_mode='Markdown'
            )
        os.unlink(file_path)
    except Exception as e:
        await update.message.reply_text(f"❌ فشل إرسال الملف: {e}")
        try:
            os.unlink(file_path)
        except:
            pass

# ================== إعداد القائمة الجانبية ==================
async def set_commands(application):
    commands = [
        BotCommand("start", "عرض القائمة الرئيسية"),
        BotCommand("help", "عرض المساعدة"),
        BotCommand("exec", "تنفيذ أمر (مثال: /exec ls -la)"),
        BotCommand("ls", "عرض الملفات في المجلد الحالي"),
        BotCommand("cd", "تغيير المجلد (مثال: /cd /home)"),
        BotCommand("sysinfo", "عرض معلومات النظام"),
        BotCommand("ps", "عرض العمليات"),
        BotCommand("kill", "إنهاء عملية (مثال: /kill 1234)"),
        BotCommand("upload", "رفع ملف"),
        BotCommand("download", "تحميل ملف (مثال: /download /path/file)"),
        BotCommand("backup", "نسخ احتياطي للمجلد (مثال: /backup /home)"),
        BotCommand("cancel", "إلغاء العملية الحالية"),
    ]
    await application.bot.set_my_commands(commands)

# ================== التشغيل ==================
def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # إضافة معالج الأوامر
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('exec', exec_command))
    application.add_handler(CommandHandler('ls', ls_command))
    application.add_handler(CommandHandler('cd', cd_command))
    application.add_handler(CommandHandler('sysinfo', sysinfo_command))
    application.add_handler(CommandHandler('ps', ps_command))
    application.add_handler(CommandHandler('kill', kill_command))
    application.add_handler(CommandHandler('upload', upload_command))
    application.add_handler(CommandHandler('download', download_command))
    application.add_handler(CommandHandler('backup', backup_command))
    application.add_handler(CommandHandler('cancel', cancel))

    # معالج الأزرار
    application.add_handler(CallbackQueryHandler(button_handler))

    # معالج الرسائل النصية
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # معالج رفع الملفات
    application.add_handler(MessageHandler(filters.Document.ALL, file_upload_handler))

    # تعيين القائمة الجانبية
    application.post_init = set_commands

    print("✅ البوت يعمل الآن ...")
    application.run_polling()

if __name__ == '__main__':
    main()