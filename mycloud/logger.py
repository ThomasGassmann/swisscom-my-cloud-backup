import os, datetime
from colorama import Fore, Style, init


init()


LOG_FILE = ''


def log(string: str, error=False, end='\n'):
    if error:
        string = f'ERR: {string}'
    formatted_time = datetime.datetime.now().strftime('%H:%M:%S')
    string = f'{formatted_time}: {string}'
    color = Fore.RED if error else Fore.WHITE
    print(f'{color}{string}{Style.RESET_ALL}', end=end)
    if LOG_FILE == '':
        return
    try:
        with open(LOG_FILE, 'a', encoding='utf8') as file:
            file.write(string)
            file.write('\n')
    except Exception as ex:
        print(f'ERR: Failed to write to log file: {str(ex)}')