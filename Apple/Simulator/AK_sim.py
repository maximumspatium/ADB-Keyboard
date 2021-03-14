# Quick & dirty 8049-based ADB keyboard simulator
# Author: Max Poliakovski 2020
#
# Usage:
# python3 sim8049.py --rom_path=[path to the AEK II firmware]

from argparse import ArgumentParser

from emu8048 import MSC48_CPU
from dasm8048 import Dasm8048

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

    # instantiate the disassembler
    dasm = Dasm8048()

    print("Welcome to the ADB keyboard simulator.")
    print("Please enter a command or 'help'.")

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
        elif cmd == "dasm":
            if len(words) == 1:
                pc = cpu_obj.get_pc()
                s,l = dasm.dasm_single(pc, bytes([rom_data[pc], rom_data[pc+1]]))
                print(s)
            elif len(words) < 3:
                print("Invalid command syntax")
                continue
            else:
                addr  = int(words[1], 0)
                count = int(words[2], 0)
                for i in range(count):
                    s,l = dasm.dasm_single(addr, bytes([rom_data[addr], rom_data[addr+1]]))
                    print(s)
                    addr += l
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
            print("step        - execute single instruction")
            print("si          - execute single instruction")
            print("until addr  - execute until addr is reached")
            print("regs        - print internal registers")
            print("dump        - dump internal memory")
            print("dasm [A N]] - disassemble N instructions at address A")
            print("              'dasm' without parameters disassembles one")
            print("              instruction at PC")
            print("set X=Y     - change value of register X to Y")
            print("adb_send X  - send byte X over ADB")
            print("quit        - shut down the simulator")
        else:
            print("Unknown command: %s" % cmd)
