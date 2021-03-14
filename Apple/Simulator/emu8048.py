'''
    Emulator for an Intel MSC-48 MCU.

    Author: Max Poliakovski 2020-2021
'''

class MSC48_CPU:
    def __init__(self, rom_size=2048, ram_size=128):
        self.rom_data = bytes()
        self.rom_size = rom_size
        self.ram_data = bytearray(ram_size)
        self.ram_size = ram_size
        self.post_instr_cb = None
        self.reset()
        self.init_io()

    def set_rom_data(self, rom_data, rom_size):
        self.rom_data = rom_data
        self.rom_size = rom_size

    def reset(self):
        self.pc  = 0  # set program counter to zero
        self.psw = 8  # init PSW, reset stack pointer
        self.rb  = 0  # select register bank O
        self.mb  = 0  # selects memory bank O
        self.bus = 0xFF # set BUS to high impedance state
        self.eie = 0  # disable external interrupts
        self.irq = 1  # interrupt line status
        self.tc  = 0
        self.tie = 0  # disable timer interrupts
        # stop timer
        self.tf  = 0  # clear timer flag
        self.f0  = 0  # clear FO
        self.f1  = 0  # clear F1
        # disable clock output from TO
        self.acc = 0
        self.cycles = 0 # number of cycles executed so far
        self.p1 = 0    # FIXME: set port 1 to input mode
        self.p2 = 0xFF # FIXME: set port 2 to input mode

    def init_io(self):
        self.t0 = 1
        self.t1 = 1

    def set_post_instr_cb(self, cb):
        ''' Set post-instruction callback '''
        self.post_instr_cb = cb

    def write_port(self, port, val):
        print("Port %d state changed to 0x%01X" % (port, val))
        if port == 1:
            self.p1 = val
        elif port == 2:
            self.p2 = val
        else:
            print("Unsupported port %d" % port)

    def get_t1_line(self):
        return self.t1

    def set_t1_line(self, val):
        self.t1 = val & 1

    def read_port1(self):
        return self.p1

    def read_port2(self):
        return self.p2

    def get_pc(self):
        return self.pc

    def get_reg_val(self, reg_num):
        return self.ram_data[self.rb * 24 + reg_num]

    def set_reg_val(self, reg_num, val):
        self.ram_data[self.rb * 24 + reg_num] = val & 0xFF

    def cond_jump(self, cond):
        if cond:
            self.pc = (self.pc & ~0xFF) | self.rom_data[self.pc]
        else: # condition false --> fall through
            self.pc = self.pc & ~0xFF | ((self.pc + 1) & 0xFF)

    def print_state(self):
        print("Register bank 0: ")
        for i in range(0, 8):
            print("r%d: 0x%01X" % (i, self.ram_data[i]))

        print("\nRegister bank 1: ")
        for i in range(0, 8):
            print("r%d: 0x%01X" % (i, self.ram_data[i+24]))

        print("\nPC : 0x%01X" % self.pc)
        print("ACC: 0x%01X" % self.acc)
        print("PSW: 0x%01X" % self.psw)
        print("Reg bank: %d" % self.rb)
        print("Mem bank: %d" % self.mb)
        print("F0: %d" % self.f0)
        print("F1: %d" % self.f1)
        print("Cycles: %d" % self.cycles)

    def dump_ram(self):
        for row in range(0, 8):
            if row != 0:
                print("")
            print("%04X  " % (row * 16), end='')
            for col in range(0, 16):
                print("%02X " % self.ram_data[row * 16 + col], end='')
        print("")

    def set_state(self, dst, val):
        if dst == "PC":
            if val < 0 or val > self.rom_size:
                print("Invalid value 0x%04X" % val)
            else:
                self.pc = val
        elif dst == "A":
            if val < 0 or val > 255:
                print("Invalid value 0x%04X" % val)
            else:
                self.acc = val
        elif dst == "T0":
            self.t0 = val & 1
        elif dst == "T1":
            self.t1 = val & 1
        elif dst.startswith("R"):
            reg_num = int(dst[1:])
            if reg_num < 0 or reg_num > 7:
                print("Invalid register %d" % reg_num)
            elif val < 0 or val > 255:
                print("Invalid value 0x%04X" % val)
            else:
                self.set_reg_val(reg_num, val)
        else:
            print("Unknown destination %s" % dst)

    def exec_until(self, addr):
        while self.pc != addr:
            self.exec_single()

    def exec_single(self):
        opcode = self.rom_data[self.pc]
        self.pc += 1 # each instruction is at least one byte wide
        self.cycles += 1 # each instruction takes at least one cycle (2.5 usecs)

        if opcode == 0x0: # NOP
            pass
        elif opcode == 0xC5: # SEL RB0
            self.rb = 0
            self.psw &= ~0x10
        elif opcode == 0xD5: # SEL RB1
            self.rb = 1
            self.psw |= 0x10
        elif opcode == 0xE5: # SEL MB0
            self.mb = 0
        elif (opcode & 0x1F) == 4: # JMP addr
            self.cycles += 1 # add extra cycle
            self.pc = (self.pc & ~0x7FF) | ((opcode & 0xE0) << 3) | self.rom_data[self.pc]
        elif (opcode & 0x1F) == 0x12: # JBb addr
            self.cycles += 1 # add extra cycle
            bit_mask = 1 << ((opcode >> 5) & 7)
            self.cond_jump(self.acc & bit_mask)
        elif (opcode & 0xFC) == 0x88: # ORL port,imm
            self.cycles += 1 # add extra cycle
            port = opcode & 3
            if port == 1:
                self.write_port(port, self.p1 | self.rom_data[self.pc])
            elif port == 2:
                self.write_port(port, self.p2 | self.rom_data[self.pc])
            else:
                print("Invalid port %d" % port)
            self.pc += 1
        elif (opcode & 0xFC) == 0x98: # ANL port,imm
            self.cycles += 1 # add extra cycle
            port = opcode & 3
            if port == 1:
                self.write_port(port, self.p1 & self.rom_data[self.pc])
            elif port == 2:
                self.write_port(port, self.p2 & self.rom_data[self.pc])
            else:
                print("Invalid port %d" % port)
            self.pc += 1
        elif opcode == 0x15: # DIS I
            self.eie = 0
        elif opcode == 0x25: # EN TCNTI
            self.tie = 1
        elif opcode == 0x35: # DIS TCNTI
            self.tie = 0
        elif opcode == 0x45: # STRT CNT
            pass
        elif opcode == 0x65: # STOP TCNT
            pass
        elif opcode == 0x85: # CLR F0
            self.f0 = 0
        elif opcode == 0xA5: # CLR F1
            self.f1 = 0
        elif (opcode & 0x1F) == 0x14: # CALL addr
            self.cycles += 1 # add extra cycle
            addr = (self.pc & ~0x7FF) | ((opcode & 0xE0) << 3) | self.rom_data[self.pc]
            self.pc += 1
            #print("addr = 0x%03X" % addr)
            if addr < self.rom_size:
                ret = (self.pc & 0xFFF) | ((self.psw & 0xF0) << 8)
                self.ram_data[(self.psw & 7) * 2 + 8] = (ret >> 8) & 0xFF
                self.ram_data[(self.psw & 7) * 2 + 9] = ret & 0xFF
                self.psw = (self.psw & 0xF8) | ((self.psw + 1) & 0x7)
                self.pc = addr
            else:
                print("Invalid destination addr 0x%03X!" % addr)
        elif opcode == 0x83: # RET
            self.cycles += 1 # add extra cycle
            stack_pos = (self.psw - 1) & 0x7
            ret = ((self.ram_data[stack_pos * 2 + 8]) << 8) | self.ram_data[stack_pos * 2 + 9]
            self.psw = (self.psw & 0xF8) | stack_pos
            self.pc = ret & 0xFFF
        elif opcode == 0x93: # RETR
            self.cycles += 1 # add extra cycle
            stack_pos = (self.psw - 1) & 0x7
            ret = ((self.ram_data[stack_pos * 2 + 8]) << 8) | self.ram_data[stack_pos * 2 + 9]
            self.psw = (self.psw & 8) | ((ret & 0xF0) >> 8) | stack_pos
            self.pc = ret & 0xFFF
        elif opcode == 0x23: # MOV A,imm
            self.cycles += 1 # add extra cycle
            self.acc = self.rom_data[self.pc]
            self.pc += 1
        elif (opcode & 0xFC) == 0x38: # OUTL port,A
            self.cycles += 1 # add extra cycle
            port = opcode & 3
            if port == 1 or port == 2:
                self.write_port(port, self.acc)
            else:
                print("Invalid port %d" % port)
        elif opcode == 0x27: # CLR A
            self.acc = 0
        elif opcode == 0x97: # CLR C
            self.psw = self.psw & 0x7F
        elif opcode == 0xD7: # MOV PSW,A
            self.psw = self.acc
        elif opcode == 0x42: # MOV A,T
            self.acc = self.tc
        elif opcode == 0x62: # MOV T,A
            self.tc = self.acc
        elif (opcode & 0xF8) == 0xB8: # MOV reg,imm
            self.cycles += 1 # add extra cycle
            self.set_reg_val(opcode & 7, self.rom_data[self.pc])
            self.pc += 1
        elif (opcode & 0xFE) == 0x10: # INC @reg
            self.ram_data[self.get_reg_val(opcode & 1)] += 1
        elif (opcode & 0xFE) == 0x20: # XCH A,@reg
            reg_num = opcode & 1
            tmp = self.ram_data[self.get_reg_val(reg_num)]
            self.ram_data[self.get_reg_val(reg_num)] = self.acc
            self.acc = tmp
        elif (opcode & 0xFE) == 0x40: # ORL A,@reg
            self.acc |= self.ram_data[self.get_reg_val(opcode & 1)]
        elif (opcode & 0xFE) == 0x60: # ADD A,@reg
            tmp = self.acc + self.ram_data[self.get_reg_val(opcode & 1)]
            self.acc = tmp & 0xFF
            if tmp > 0xFF:
                self.psw |= 0x80 # set carry
            else:
                self.psw &= 0x7F # clear carry
        elif (opcode & 0xFE) == 0xD0: # XRL A,@reg
            self.acc ^= self.ram_data[self.get_reg_val(opcode & 1)]
        elif (opcode & 0xFE) == 0x90: # MOVX @reg,A
            self.cycles += 1 # add extra cycle
        elif (opcode & 0xFE) == 0xA0: # MOV @reg,A
            self.ram_data[self.get_reg_val(opcode & 1)] = self.acc
        elif (opcode & 0xFE) == 0xF0: # MOV A,@reg
            self.acc = self.ram_data[self.get_reg_val(opcode & 1)]
        elif (opcode & 0xFE) == 0xB0: # MOV @reg,imm
            self.cycles += 1 # add extra cycle
            self.ram_data[self.get_reg_val(opcode & 1)] = self.rom_data[self.pc]
            self.pc += 1
        elif (opcode & 0xF8) == 0xE8: # DJNZ reg,addr
            self.cycles += 1 # add extra cycle
            reg_num = opcode & 7
            self.set_reg_val(reg_num, self.get_reg_val(reg_num) - 1)
            if self.get_reg_val(reg_num) != 0:
                self.pc = (self.pc & ~0xFF) | self.rom_data[self.pc]
            else:
                self.pc += 1
        elif opcode == 0x26: # JNT0 addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.t0 ^ 1)
        elif opcode == 0x36: # JT0 addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.t0)
        elif opcode == 0x46: # JNT1 addr
            #if self.adb_state:
            #    self.adb_transact()
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.t1 ^ 1)
        elif opcode == 0x56: # JT1 addr
            #if self.adb_state:
            #    self.adb_transact()
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.t1)
        elif opcode == 0x76: # JF1 addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.f1)
        elif opcode == 0x86: # JNI addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.irq ^ 1)
        elif opcode == 0x96: # JNZ addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.acc)
        elif opcode == 0xB6: # JF0 addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.f0)
        elif opcode == 0xC6: # JZ addr
            self.cycles += 1 # add extra cycle
            if self.acc == 0:
                cond = 1
            else:
                cond = 0
            self.cond_jump(cond)
        elif opcode == 0xE6: # JNC addr
            self.cycles += 1 # add extra cycle
            self.cond_jump((self.psw & 0x80) ^ 0x80)
        elif opcode == 0xF6: # JC addr
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.psw & 0x80)
        elif opcode == 0xB3: # JMPP @A
            self.cycles += 1 # add extra cycle
            cur_page = self.pc & 0xF00
            offset = self.rom_data[cur_page | (self.acc & 0xFF)]
            self.pc = cur_page | offset
        elif (opcode & 0xF8) == 0xF8: # MOV A,reg
            self.acc = self.get_reg_val(opcode & 7)
        elif (opcode & 0xF8) == 0xA8: # MOV reg,A
            self.set_reg_val(opcode & 7, self.acc)
        elif (opcode & 0xF8) == 0x58: # ANL A,reg
            self.acc &= self.get_reg_val(opcode & 7)
        elif (opcode & 0xF8) == 0x68: # ADD A,reg
            tmp = self.acc + self.get_reg_val(opcode & 7)
            self.acc = tmp & 0xFF
            if tmp > 0xFF:
                self.psw |= 0x80 # set carry
            else:
                self.psw &= 0x7F # clear carry
        elif opcode == 0x3: # ADD A,imm
            self.cycles += 1 # add extra cycle
            tmp = self.acc + self.rom_data[self.pc]
            self.acc = tmp & 0xFF
            if tmp > 0xFF:
                self.psw |= 0x80 # set carry
            else:
                self.psw &= 0x7F # clear carry
            self.pc += 1
        elif opcode == 0x43: # ORL A,imm
            self.cycles += 1 # add extra cycle
            self.acc |= self.rom_data[self.pc]
            self.pc += 1
        elif opcode == 0x53: # ANL A,imm
            self.cycles += 1 # add extra cycle
            self.acc &= self.rom_data[self.pc]
            self.pc += 1
        elif opcode == 0xD3: # XRL A,imm
            self.cycles += 1 # add extra cycle
            self.acc ^= self.rom_data[self.pc]
            self.pc += 1
        elif opcode == 0x7: # DEC A
            self.acc = (self.acc - 1) & 0xFF
        elif opcode == 0x17: # INC A
            self.acc = (self.acc + 1) & 0xFF
        elif (opcode & 0xF8) == 0x18: # INC reg
            reg_num = opcode & 7
            self.set_reg_val(reg_num, self.get_reg_val(reg_num) + 1)
        elif (opcode & 0xF8) == 0xC8: # DEC reg
            reg_num = opcode & 7
            self.set_reg_val(reg_num, self.get_reg_val(reg_num) - 1)
        elif opcode == 0x95: # CPL F0
            self.f0 ^= 1
        elif opcode == 0xB5: # CPL F1
            self.f1 ^= 1
        elif opcode == 0x37: # CPL A
            self.acc = ~self.acc & 0xFF
        elif opcode == 0x47: # SWAP A
            self.acc = ((self.acc & 0xF) << 4) | ((self.acc & 0xF0) >> 4)
        elif opcode == 0xA7: # CPL C
            self.psw = (self.psw ^ 0x80) & 0xFF
        elif opcode == 0x77: # RR A
            self.acc = ((self.acc >> 1) & 0x7F) | ((self.acc & 1) << 7)
        elif opcode == 0xE7: # RL A
            self.acc = ((self.acc << 1) & 0xFE) | ((self.acc >> 7) & 1)
        elif opcode == 0x67: # RRC A
            tmp = self.psw
            self.psw = (((self.acc & 1) << 7) | (self.psw & 0x7F)) & 0xFF
            self.acc = ((self.acc >> 1) & 0xFF) | (tmp & 0x80)
        elif opcode == 0xF7: # RLC A
            tmp = self.psw
            self.psw = ((self.acc & 0x80) | (self.psw & 0x7F)) & 0xFF
            self.acc = ((self.acc << 1) & 0xFE) | ((tmp >> 7) & 1)
        elif (opcode & 0xF8) == 0x28: # XCH A,reg
            reg_num = opcode & 7
            tmp = self.get_reg_val(reg_num)
            self.set_reg_val(reg_num, self.acc)
            self.acc = tmp
        elif (opcode & 0xF8) == 0xD8: # XRL A,reg
            self.acc = (self.acc ^ self.get_reg_val(opcode & 7)) & 0xFF
        elif (opcode & 0xF8) == 0x48: # ORL A,reg
            self.acc = (self.acc | self.get_reg_val(opcode & 7)) & 0xFF
        elif (opcode & 0xFC) == 0x8:
            self.cycles += 1 # add extra cycle
            port = opcode & 3
            if port == 0: # INS A,BUS
                self.acc = self.bus
            elif port == 1: # IN A,p1
                self.acc = self.p1
            elif port == 2: # IN A,p2
                self.acc = self.p2
            else:
                print("Invalid port %d" % port)
        elif opcode == 0xE3: # MOVP3 A, @A
            self.cycles += 1 # add extra cycle
            self.acc = self.rom_data[0x300 | self.acc]
        else:
            print("Unknown opcode 0x%01X at 0x%03X" % (opcode, self.pc - 1))

        if self.post_instr_cb:
            self.post_instr_cb(self.cycles)
