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
    QLineEdit,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QMessageBox,
)

from linkedin_scraper import BrowserManager, PersonScraper, wait_for_manual_login
from gui_helpers import model_to_dict, save_profile_outputs


SESSION_PATH = ".linkedin_gui_session.json"


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


class ScrapeWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, profile_url: str, output_dir: str):
        super().__init__()
        self.profile_url = profile_url
        self.output_dir = output_dir

    def run(self):
        try:
            result = asyncio.run(self.scrape_profile())
            self.done.emit(True, result)
        except Exception as e:
            self.done.emit(False, str(e))

    async def scrape_profile(self):
        self.log.emit("Opening browser with saved login session...")

        async with BrowserManager(headless=False) as browser:
            await browser.load_session(SESSION_PATH)

            self.log.emit("Creating profile scraper...")
            scraper = PersonScraper(browser.page)

            self.log.emit(f"Scraping profile: {self.profile_url}")
            person = await scraper.scrape(self.profile_url)

            person_data = model_to_dict(person)

            self.log.emit("Saving Markdown and JSON...")
            md_path, json_path = save_profile_outputs(person_data, self.output_dir)

            return f"Saved:\n{md_path}\n{json_path}"


class LinkedInScraperGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LinkedIn Profile Saver")
        self.resize(760, 520)

        self.login_worker = None
        self.scrape_worker = None
        self.logged_in = Path(SESSION_PATH).exists()

        layout = QVBoxLayout()

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("LinkedIn Profile URL"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.linkedin.com/in/example/")
        layout.addWidget(self.url_input)

        output_row = QHBoxLayout()
        self.output_input = QLineEdit("output")
        self.output_button = QPushButton("Choose Output Folder")
        self.output_button.clicked.connect(self.choose_output_folder)

        output_row.addWidget(QLabel("Output:"))
        output_row.addWidget(self.output_input)
        output_row.addWidget(self.output_button)

        layout.addLayout(output_row)

        button_row = QHBoxLayout()

        self.login_button = QPushButton("Login to LinkedIn")
        self.login_button.clicked.connect(self.start_login)

        self.scrape_button = QPushButton("Scrape One Profile")
        self.scrape_button.clicked.connect(self.scrape_profile)

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
            self.status_label.setText("Status: LinkedIn session found. You can scrape a profile.")
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
                "LinkedIn login complete. You can now scrape one profile at a time.",
            )
        else:
            self.log(f"Login failed: {message}")
            QMessageBox.critical(self, "Login failed", message)

        self.refresh_status()

    def scrape_profile(self):
        profile_url = self.url_input.text().strip()
        output_dir = self.output_input.text().strip()

        if not Path(SESSION_PATH).exists():
            QMessageBox.warning(
                self,
                "Not logged in",
                "Please log into LinkedIn first.",
            )
            self.refresh_status()
            return

        if not profile_url:
            QMessageBox.warning(
                self,
                "Missing URL",
                "Paste a LinkedIn profile URL first.",
            )
            return

        if "linkedin.com/in/" not in profile_url:
            QMessageBox.warning(
                self,
                "Profile URL expected",
                "This minimalist GUI only supports single person profile URLs.",
            )
            return

        self.login_button.setEnabled(False)
        self.scrape_button.setEnabled(False)

        self.log("Starting profile scrape...")

        self.scrape_worker = ScrapeWorker(
            profile_url=profile_url,
            output_dir=output_dir,
        )

        self.scrape_worker.log.connect(self.log)
        self.scrape_worker.done.connect(self.scrape_done)
        self.scrape_worker.start()

    def scrape_done(self, success: bool, message: str):
        self.login_button.setEnabled(True)
        self.scrape_button.setEnabled(True)

        if success:
            self.log(message)
            QMessageBox.information(self, "Profile saved", message)
        else:
            self.log(f"Scrape failed: {message}")
            QMessageBox.critical(self, "Scrape failed", message)

        self.refresh_status()


def main():
    app = QApplication(sys.argv)
    window = LinkedInScraperGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
