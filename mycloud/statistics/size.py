import sys

from hurry.filesize import size

from mycloud.drive import DriveClient


async def calculate_size(client: DriveClient, directory: str):
    original_out = sys.stdout
    sys.stdout = None
    summed_up = 0
    longest_string = 0
    file_count = 0
    async for file in client.list_files(directory):
        file_count += 1
        original_out.write(str(' ' * longest_string) + '\r')
        to_print = 'Bytes: {} | Size (readable): {} | Count: {}'.format(
            summed_up, size(summed_up), file_count)
        if len(to_print) > longest_string:
            longest_string = len(to_print)

        original_out.write(to_print)
        summed_up += int(file['Length'])

    sys.stdout = original_out
