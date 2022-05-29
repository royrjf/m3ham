#!/usr/bin/python3


custom_crc_table = {}

def int_to_bytes(i):
    return [(i >> 24) & 0xFF, (i >> 16) & 0xFF, (i >> 8) & 0xFF, i & 0xFF]


def generate_crc32_table(_poly):

    global custom_crc_table

    for i in range(256):
        c = i << 24

        for j in range(8):
            c = (c << 1) ^ _poly if (c & 0x80000000) else c << 1

        custom_crc_table[i] = c & 0xffffffff


def custom_crc32(buf):

    global custom_crc_table
    crc = 0xffffffff

    for integer in buf:
        b = int_to_bytes(integer)

        for byte in b:
            crc = ((crc << 8) & 0xffffffff) ^ custom_crc_table[(crc >> 24) ^ byte]
    return crc

poly = 0x04C11DB7
# buf = [1, 2, 3, 4, 5]
generate_crc32_table(poly)

if __name__ == "__main__":

    print(hex(custom_crc32(map(ord, 'B,PUSH,0f_0_0_0_2_,'))))
    # print(hex(custom_crc32([1,2,3,4,5])))

    def cmd(cmd, a,b,c,d,e):

        dev = serial.Serial('/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DO01N09I-if00-port0', 115200, timeout=2.5)
        
        cmd = 'B,%s,%s_%s_%s_%s_%s,' %(cmd, a,b,c,e,d)
        crc = custom_crc32(map(ord, cmd)).to_bytes(4, byteorder='big')
        cmd = cmd.encode()
        cmd += crc

        dev.write(cmd)
        print(cmd)
        #time.sleep(0.1)
        print(dev.readline())
        #print(dev.readall())
