import sys
import asyncio
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QSpinBox,
)

from linkedin_scraper import BrowserManager, PersonScraper, wait_for_manual_login
from gui_helpers import model_to_dict, save_profile_outputs


SESSION_PATH = ".linkedin_gui_session.json"
MAX_URLS_PER_RUN = 10


def normalize_urls(raw_text: str) -> list[str]:
    urls = []

    for line in raw_text.splitlines():
        line = line.strip()

        if not line:
            continue

        if "linkedin.com/in/" not in line:
            continue

        # Remove obvious trailing junk
        line = line.split()[0].strip()

        if line not in urls:
            urls.append(line)

    return urls[:MAX_URLS_PER_RUN]


class LoginWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def run(self):
        try:
            asyncio.run(self.login())
            self.done.emit(True, SESSION_PATH)
        except Exception as e:
            self.done.emit(False, str(e))

    async def login(self):
        self.log.emit("Opening LinkedIn login window...")

        async with BrowserManager(headless=False) as browser:
            await browser.page.goto("https://www.linkedin.com/login")

            self.log.emit("Please log into LinkedIn in the browser window.")
            self.log.emit("Use your own email/password directly on LinkedIn.")
            self.log.emit("This app does not see or store your password.")
            self.log.emit("Complete any 2FA or CAPTCHA if LinkedIn asks.")
            self.log.emit("Waiting for LinkedIn login to finish...")

            await wait_for_manual_login(browser.page, timeout=300000)

            self.log.emit("Login detected. Saving local browser session...")
            await browser.save_session(SESSION_PATH)

            self.log.emit("Login session saved.")


class BatchScrapeWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, profile_urls: list[str], output_dir: str, delay_seconds: int):
        super().__init__()
        self.profile_urls = profile_urls
        self.output_dir = output_dir
        self.delay_seconds = delay_seconds

    def run(self):
        try:
            result = asyncio.run(self.scrape_profiles())
            self.done.emit(True, result)
        except Exception as e:
            self.done.emit(False, str(e))

    async def scrape_profiles(self):
        total = len(self.profile_urls)
        saved_count = 0
        failed_count = 0
        saved_files = []

        self.log.emit(f"Opening browser with saved login session...")
        self.log.emit(f"Profiles queued: {total}")

        async with BrowserManager(headless=False) as browser:
            await browser.load_session(SESSION_PATH)

            scraper = PersonScraper(browser.page)

            for index, profile_url in enumerate(self.profile_urls, start=1):
                self.log.emit("")
                self.log.emit(f"[{index}/{total}] Scraping: {profile_url}")

                try:
                    person = await scraper.scrape(profile_url)
                    person_data = model_to_dict(person)

                    md_path, json_path = save_profile_outputs(person_data, self.output_dir)

                    saved_count += 1
                    saved_files.append(str(md_path))

                    self.log.emit(f"[{index}/{total}] Saved Markdown: {md_path}")
                    self.log.emit(f"[{index}/{total}] Saved JSON: {json_path}")

                except Exception as e:
                    failed_count += 1
                    self.log.emit(f"[{index}/{total}] Failed: {e}")
                    self.log.emit("Stopping batch to avoid repeated failed requests.")
                    break

                if index < total:
                    self.log.emit(f"Waiting {self.delay_seconds} seconds before next profile...")
                    await asyncio.sleep(self.delay_seconds)

        summary = (
            f"Batch complete.\n"
            f"Saved: {saved_count}\n"
            f"Failed: {failed_count}\n"
            f"Output folder: {self.output_dir}"
        )

        if saved_files:
            summary += "\n\nMarkdown files:\n" + "\n".join(saved_files)

        return summary


class LinkedInScraperGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinkedIn Profile Saver")
        self.resize(820, 640)

        self.login_worker = None
        self.scrape_worker = None
        self.logged_in = Path(SESSION_PATH).exists()

        layout = QVBoxLayout()

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("LinkedIn Profile URLs - paste 1 to 10 profile URLs, one per line"))
        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "https://www.linkedin.com/in/example-one/\n"
            "https://www.linkedin.com/in/example-two/"
        )
        self.url_input.setFixedHeight(120)
        layout.addWidget(self.url_input)

        output_row = QHBoxLayout()
        self.output_input = QLineEdit("output")
        self.output_button = QPushButton("Choose Output Folder")
        self.output_button.clicked.connect(self.choose_output_folder)

        output_row.addWidget(QLabel("Output:"))
        output_row.addWidget(self.output_input)
        output_row.addWidget(self.output_button)

        layout.addLayout(output_row)

        settings_row = QHBoxLayout()

        self.delay_spinbox = QSpinBox()
        self.delay_spinbox.setMinimum(10)
        self.delay_spinbox.setMaximum(300)
        self.delay_spinbox.setValue(45)
        self.delay_spinbox.setSingleStep(5)

        settings_row.addWidget(QLabel("Delay between profiles, seconds:"))
        settings_row.addWidget(self.delay_spinbox)
        settings_row.addStretch()

        layout.addLayout(settings_row)

        button_row = QHBoxLayout()

        self.login_button = QPushButton("Login to LinkedIn")
        self.login_button.clicked.connect(self.start_login)

        self.scrape_button = QPushButton("Scrape URLs")
        self.scrape_button.clicked.connect(self.scrape_profiles)

        button_row.addWidget(self.login_button)
        button_row.addWidget(self.scrape_button)

        layout.addLayout(button_row)

        layout.addWidget(QLabel("Log"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self.setLayout(layout)
        self.refresh_status()

        QTimer.singleShot(600, self.startup_login_prompt)

    def refresh_status(self):
        self.logged_in = Path(SESSION_PATH).exists()

        if self.logged_in:
            self.status_label.setText(
                "Status: LinkedIn session found. You can scrape up to 10 profile URLs."
            )
            self.scrape_button.setEnabled(True)
        else:
            self.status_label.setText("Status: Not logged in. Please log in first.")
            self.scrape_button.setEnabled(False)

    def log(self, message: str):
        self.log_box.append(message)

    def startup_login_prompt(self):
        if not Path(SESSION_PATH).exists():
            reply = QMessageBox.question(
                self,
                "LinkedIn login required",
                "To use this tool, log into LinkedIn manually in a browser window.\n\nOpen LinkedIn login now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.start_login()
        else:
            self.log("Existing LinkedIn session found.")

    def choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose output folder",
            self.output_input.text(),
        )

        if folder:
            self.output_input.setText(folder)

    def start_login(self):
        self.login_button.setEnabled(False)
        self.scrape_button.setEnabled(False)

        self.log("Starting LinkedIn login process...")

        self.login_worker = LoginWorker()
        self.login_worker.log.connect(self.log)
        self.login_worker.done.connect(self.login_done)
        self.login_worker.start()

    def login_done(self, success: bool, message: str):
        self.login_button.setEnabled(True)

        if success:
            self.log(f"Login complete. Session saved to: {message}")
            QMessageBox.information(
                self,
                "Login complete",
                "LinkedIn login complete. You can now scrape profile URLs.",
            )
        else:
            self.log(f"Login failed: {message}")
            QMessageBox.critical(self, "Login failed", message)

        self.refresh_status()

    def scrape_profiles(self):
        raw_urls = self.url_input.toPlainText()
        profile_urls = normalize_urls(raw_urls)
        output_dir = self.output_input.text().strip()
        delay_seconds = self.delay_spinbox.value()

        if not Path(SESSION_PATH).exists():
            QMessageBox.warning(
                self,
                "Not logged in",
                "Please log into LinkedIn first.",
            )
            self.refresh_status()
            return

        if not profile_urls:
            QMessageBox.warning(
                self,
                "Missing URLs",
                "Paste between 1 and 10 LinkedIn profile URLs first.",
            )
            return

        pasted_count = len([line for line in raw_urls.splitlines() if line.strip()])

        if pasted_count > MAX_URLS_PER_RUN:
            QMessageBox.information(
                self,
                "URL limit",
                f"This app processes a maximum of {MAX_URLS_PER_RUN} URLs per run.\n\n"
                f"Only the first {MAX_URLS_PER_RUN} valid profile URLs will be used.",
            )

        confirm = QMessageBox.question(
            self,
            "Confirm batch scrape",
            f"Process {len(profile_urls)} profile URL(s) one at a time?\n\n"
            f"Delay between profiles: {delay_seconds} seconds\n"
            f"Maximum per run: {MAX_URLS_PER_RUN}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.login_button.setEnabled(False)
        self.scrape_button.setEnabled(False)

        self.log("Starting profile batch...")

        self.scrape_worker = BatchScrapeWorker(
            profile_urls=profile_urls,
            output_dir=output_dir,
            delay_seconds=delay_seconds,
        )

        self.scrape_worker.log.connect(self.log)
        self.scrape_worker.done.connect(self.scrape_done)
        self.scrape_worker.start()

    def scrape_done(self, success: bool, message: str):
        self.login_button.setEnabled(True)
        self.scrape_button.setEnabled(True)

        if success:
            self.log("")
            self.log(message)
            QMessageBox.information(self, "Batch complete", message)
        else:
            self.log(f"Batch failed: {message}")
            QMessageBox.critical(self, "Batch failed", message)

        self.refresh_status()


def main():
    app = QApplication(sys.argv)
    window = LinkedInScraperGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
