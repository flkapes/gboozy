import os, gzip


def read_file(fname, compress=False):
    if compress:
        f = gzip.GzipFile(fname, 'rb')
    else:
        f = open(fname, 'rb')
    try:
        data = f.read()
    finally:
        f.close()
    return data


def write_file(data, fname, compress=True):
    # print(os.getcwd())

    if compress:
        f = gzip.GzipFile(fname, 'wb')
    else:
        f = open(fname, 'wb')
    try:
        f.write(data)
    finally:
        f.close()


if __name__ == '__main__':
    pa = "logs"
    for log in os.listdir(pa):
        if log.endswith(".log"):
            write_file(read_file("logs/" + log, compress=False), f"{'logs/' + log.split('.')[0]}+.gz", compress=True)
            os.remove("logs/" + log)
