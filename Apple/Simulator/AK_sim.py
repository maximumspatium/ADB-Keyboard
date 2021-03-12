# Quick & dirty 8049-based ADB keyboard simulator
# Author: Max Poliakovski 2020
#
# Usage:
# python3 sim8049.py --rom_path=[path to the AEK II firmware]

from argparse import ArgumentParser

from emu8048 import MSC48_CPU

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('--rom_path', type=str,
                        dest='rom_path',
                        help='path to 8048/8049 ROM file to process',
                        metavar='ROM_PATH', required=True)

    opts = parser.parse_args()

    cpu_obj = MSC48_CPU()

    with open(opts.rom_path, 'rb') as rom_file:
        rom_file.seek(0, 2)
        rom_size = rom_file.tell()
        print("ROM file size %d bytes" % rom_size)

        # load ROM image in the the CPU object
        rom_file.seek(0, 0)
        rom_data = rom_file.read();
        cpu_obj.set_rom_data(rom_data, rom_size)

    #------- DISASSEMBLER TEST --------
    from dasm8048 import Dasm8048

    dasm = Dasm8048()
    print(dasm.dasm_single(0, bytes([0xE5,1]))[0])
    dasm.set_uppercase(True)
    print(dasm.dasm_single(0, bytes([0xE5,1]))[0])
    dasm.set_opcode_width(20)
    print(dasm.dasm_single(0, bytes([0xE5,1]))[0])
    dasm.set_uppercase(False)

    #----------------------------------

    cmd = ""
    prev_cmd = ""

    while cmd != "quit":
        inp_str = input("> ")

        if inp_str == "":
            if prev_cmd != "":
                inp_str = prev_cmd
            else:
                continue

        prev_cmd = inp_str

        words = inp_str.split()
        cmd = words[0]

        if cmd == "quit":
            pass
        elif cmd == "step" or cmd == "si":
            cpu_obj.exec_single()
        elif cmd == "until":
            if len(words) < 2:
                print("Invalid command syntax")
                continue
            addr = int(words[1], 0)
            print("Execute until 0x%03X" % addr)
            cpu_obj.exec_until(addr)
        elif cmd == "regs":
            cpu_obj.print_state()
        elif cmd == "dump":
            cpu_obj.dump_ram()
        elif cmd == "set":
            if len(words) < 2:
                print("Invalid command syntax")
                continue
            args = words[1].split('=')
            if len(args) < 2:
                print("Invalid command syntax")
                continue
            dst = args[0].upper()
            val = int(args[1], 0)
            cpu_obj.set_state(dst, val)
        elif cmd == "adb_send":
            if len(words) < 2:
                print("Invalid command syntax")
                continue
            adb_cmd = int(words[1], 0)
            print("Sending ADB command 0x%01X" % adb_cmd)
            cpu_obj.adb_send(adb_cmd)
        elif cmd == "help":
            print("step       - execute single instruction")
            print("si         - execute single instruction")
            print("until addr - execute until addr is reached")
            print("regs       - print internal registers")
            print("dump       - dump internal memory")
            print("set X=Y    - change value of register X to Y")
            print("adb_send X - send byte X over ADB")
            print("quit       - shut down the simulator")
        else:
            print("Unknown command: %s" % cmd)
