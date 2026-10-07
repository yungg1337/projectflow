#!/usr/bin/env python3
"""Запуск приложения «ProjectFlow».

Использование:
    python run.py            # сервер на http://127.0.0.1:8000
    python run.py --port 9000
"""
import argparse

from app import config, db, server


def main():
    """Разбирает аргументы командной строки и запускает сервер."""
    parser = argparse.ArgumentParser(description="Информационная система ProjectFlow")
    parser.add_argument("--host", default=config.HOST, help="адрес сервера")
    parser.add_argument("--port", type=int, default=config.PORT, help="порт сервера")
    parser.add_argument("--reset", action="store_true",
                        help="удалить базу данных и создать её заново")
    args = parser.parse_args()

    if args.reset and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    config.ensure_dirs()
    db.init_db()
    print("ProjectFlow запущен: http://{}:{}".format(args.host, args.port))
    print("Демонстрационные входы: admin@example.com / admin12345,")
    print("                       manager@example.com / manager12345,")
    print("                       executor@example.com / executor12345")
    server.serve_forever(args.host, args.port)


if __name__ == "__main__":
    main()
