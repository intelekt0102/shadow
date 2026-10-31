import io
import os
import subprocess
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
import speech_recognition as sr
import imageio_ffmpeg
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class SubtitleApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Audio to SRT Subtitr Yaratuvchi")
        self.geometry("720x540")

        # Papka yoki fayl tanlash
        self.path_frame = ctk.CTkFrame(self)
        self.path_frame.pack(pady=15, padx=20, fill="x")

        self.path_entry = ctk.CTkEntry(self.path_frame, placeholder_text="Audio fayl yoki papka manzili...")
        self.path_entry.pack(side="left", padx=(10, 10), pady=10, fill="x", expand=True)

        self.btn_file = ctk.CTkButton(self.path_frame, text="Fayl tanlash", width=110, command=self.select_file)
        self.btn_file.pack(side="left", padx=5)

        self.btn_folder = ctk.CTkButton(self.path_frame, text="Papka tanlash", width=110, command=self.select_folder)
        self.btn_folder.pack(side="left", padx=(5, 10))

        # Sozlamalar
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.pack(pady=5, padx=20, fill="x")

        ctk.CTkLabel(self.settings_frame, text="Til:").pack(side="left", padx=(15, 5), pady=10)
        self.lang_var = ctk.StringVar(value="ar-SA")
        self.lang_menu = ctk.CTkOptionMenu(
            self.settings_frame,
            variable=self.lang_var,
            values=["ar-SA", "ru-RU", "uz-UZ", "en-US"]
        )
        self.lang_menu.pack(side="left", padx=5)

        # Boshlash tugmasi
        self.start_btn = ctk.CTkButton(
            self,
            text="SRT Subtitr yaratishni boshlash",
            height=42,
            font=("Arial", 15, "bold"),
            command=self.start_thread
        )
        self.start_btn.pack(pady=12, padx=20, fill="x")

        # Log oynasi
        self.log_box = ctk.CTkTextbox(self, height=270, font=("Consolas", 13))
        self.log_box.pack(pady=10, padx=20, fill="both", expand=True)

    def log(self, message):
        self.after(0, self._append_log, message)

    def _append_log(self, message):
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Audio fayllar", "*.mp3 *.wav *.m4a *.ogg")])
        if file_path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, file_path)

    def select_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder_path)

    def format_srt_time(self, milliseconds: int) -> str:
        milliseconds = max(0, int(milliseconds))
        seconds = milliseconds // 1000
        millis = milliseconds % 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def convert_to_wav(self, audio_path):
        wav_path = os.path.splitext(audio_path)[0] + "_temp_16k.wav"
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        subprocess.run(
            [ffmpeg_exe, "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            check=True
        )
        return wav_path, True

    def start_thread(self):
        target_path = self.path_entry.get().strip()
        if not target_path or not os.path.exists(target_path):
            messagebox.showwarning("Xatolik", "Iltimos, audio fayl yoki papkani tanlang!")
            return
        self.start_btn.configure(state="disabled", text="Subtitr tayyorlanmoqda...")
        threading.Thread(target=self.process_audio, args=(target_path,), daemon=True).start()

    def process_audio(self, target_path):
        recognizer = sr.Recognizer()
        lang = self.lang_var.get()

        try:
            files = []
            if os.path.isfile(target_path):
                files = [target_path]
            else:
                exts = (".wav", ".mp3", ".m4a", ".ogg")
                files = [
                    os.path.join(target_path, f)
                    for f in os.listdir(target_path)
                    if f.lower().endswith(exts) and not f.lower().endswith("_temp_16k.wav")
                ]

            if not files:
                self.log("[!] Audio fayllar topilmadi.")
                return

            self.log(f"[*] Jami ishlov beriladigan audiolar: {len(files)} ta.\n")

            for idx, audio_path in enumerate(files, 1):
                base_name = os.path.splitext(audio_path)[0]
                file_name = os.path.basename(audio_path)
                self.log(f"--- [{idx}/{len(files)}] Subtitr tuzilmoqda: {file_name} ---")

                wav_path, is_temp = self.convert_to_wav(audio_path)
                try:
                    sound = AudioSegment.from_wav(wav_path)
                    total_len = len(sound)

                    # Ovozli qismlarning aniq boshlanish va tugash vaqtlarini (ms) aniqlash
                    silence_thresh = sound.dBFS - 14 if sound.dBFS != float("-inf") else -40
                    nonsilent_ranges = detect_nonsilent(
                        sound,
                        min_silence_len=500,
                        silence_thresh=silence_thresh,
                        seek_step=10
                    )

                    srt_content = []
                    txt_content = []
                    sub_index = 1
                    keep_silence = 200  # So'z boshi va oxiri uzilib qolmasligi uchun (ms)

                    for start_ms, end_ms in nonsilent_ranges:
                        # 200 ms dan qisqa tasodifiy shovqinlarni o'tkazib yuborish
                        if (end_ms - start_ms) < 200:
                            continue

                        # Ovozni tanish uchun atrofidan ozgina zahira bilan qirqib olamiz
                        pad_start = max(0, start_ms - keep_silence)
                        pad_end = min(total_len, end_ms + keep_silence)
                        chunk = sound[pad_start:pad_end]

                        # Diskka yozmasdan RAM (BytesIO) orqali uzatamiz
                        wav_buffer = io.BytesIO()
                        chunk.export(wav_buffer, format="wav")
                        wav_buffer.seek(0)

                        try:
                            with sr.AudioFile(wav_buffer) as source:
                                audio_data = recognizer.record(source)
                                text = recognizer.recognize_google(audio_data, language=lang).strip()

                            if text:
                                # Subtitr uchun haqiqiy start_ms va end_ms vaqtlarini yozamiz
                                start_str = self.format_srt_time(start_ms)
                                end_str = self.format_srt_time(end_ms)

                                srt_entry = f"{sub_index}\n{start_str} --> {end_str}\n{text}\n"
                                srt_content.append(srt_entry)
                                txt_content.append(text)

                                self.log(f"[{start_str} --> {end_str}] {text}")
                                sub_index += 1
                        except sr.UnknownValueError:
                            pass
                        except Exception as e:
                            self.log(f"[Bo'lak xatosi]: {e}")

                    # SRT va TXT fayllarni saqlash
                    srt_file_path = f"{base_name}.srt"
                    with open(srt_file_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(srt_content))

                    txt_file_path = f"{base_name}.txt"
                    with open(txt_file_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(txt_content))

                    self.log(f"[+] SRT subtitr saqlandi: {srt_file_path}")
                    self.log(f"[+] TXT matn saqlandi: {txt_file_path}\n")

                finally:
                    if is_temp and os.path.exists(wav_path):
                        try:
                            os.remove(wav_path)
                        except OSError:
                            pass

            self.log("=== BARCHA AUDIOLARNING SRT SUBTITRI TAYYOR! ===")
        except Exception as e:
            self.log(f"[XATO]: {str(e)}")
        finally:
            self.after(0, lambda: self.start_btn.configure(state="normal", text="SRT Subtitr yaratishni boshlash"))


if __name__ == "__main__":
    app = SubtitleApp()
    app.mainloop()