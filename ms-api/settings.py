# # settings.py
# from pydantic import BaseSettings
#
# class Settings(BaseSettings):
#     database_url: str
#
#     class Config:
#         env_file = ".env"        # <- имя файла с переменными
#         env_file_encoding = "utf-8"
#
# settings = Settings()          # при импорте автоматически загрузит .env
