

class MSC48_CPU:
    def __init__(self, rom_size=2048, ram_size=128):
        self.rom_data = bytes()
        self.rom_size = rom_size
        self.ram_data = bytearray(ram_size)
        self.ram_size = ram_size
        self.init_state()
        self.init_io()

    def set_rom_data(self, rom_data, rom_size):
        self.rom_data = rom_data
        self.rom_size = rom_size

    def init_state(self):
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
        self.t0 = 1 # right option is released
        self.t1 = 1 # set ADB input high
        self.adb_state = 0 # no ADB transaction pending
        self.adb_next_state = 0
        self.adb_cyc_cnt = 0 # ADB cycles counter
        self.adb_cmd = 0
        self.adb_bit = 0
        self.adb_low_time = 0
        self.adb_high_time = 0
        self.adb_phase = 0
        self.adb_byte = 0
        self.adb_bit = 0
        self.adb_bit_pos = 0
        self.adb_data = bytearray()

    def adb_send(self, adb_cmd):
        self.adb_cmd = adb_cmd
        self.adb_data = bytearray()
        self.adb_state = 1

    def adb_transact(self):
        if self.adb_state == 1: # init ADB transaction
            print("ADB transaction start")
            self.adb_cyc_cnt = self.cycles
            self.t1 = 0
            self.adb_state = 2
        elif self.adb_state == 2: # generate attention (T1 low for 800 usecs)
            if (self.cycles - self.adb_cyc_cnt) >= 320:
                print("ADB attention ended")
                self.adb_cyc_cnt = self.cycles
                self.t1 = 1
                self.adb_state = 3
        elif self.adb_state == 3: # Sync (T1 high for 70 usecs)
            if (self.cycles - self.adb_cyc_cnt) >= 28:
                print("ADB Sync ended")
                self.adb_bit = 7
                self.adb_cyc_cnt = self.cycles
                self.t1 = 0 # each bit cell starts low
                self.adb_state = 4
        elif self.adb_state == 4: # send command byte
            if self.adb_bit >= 0:
                if (self.cycles - self.adb_cyc_cnt) < 40: # 100 usecs cells
                    if (self.adb_cmd & (1 << self.adb_bit)): # bit=1
                        if (self.cycles - self.adb_cyc_cnt) >= 14:
                            self.t1 = 1 # go high after 35 usecs
                    else: # bit=0
                        if (self.cycles - self.adb_cyc_cnt) >= 26:
                            self.t1 = 1 # go high after 65 usecs
                else:
                    print("Sending next ADB bit")
                    self.t1 = 0 # each bit cell starts low
                    self.adb_bit -= 1
                    if self.adb_bit < 0:
                        print("Sending ADB byte completed")
                        print("Sending STOP bit")
                        self.adb_state = 5
                    self.adb_cyc_cnt = self.cycles
            else:
                print("ADB command byte already completed")
                self.adb_state = 0 # abort transaction
        elif self.adb_state == 5: # stop bit
            if (self.cycles - self.adb_cyc_cnt) >= 28:
                self.t1 = 1 # go high after 70 usecs
                print("ADB stop bit completed")
                self.adb_cyc_cnt = self.cycles
                self.adb_state = 6
        elif self.adb_state == 6: # Tlt (T1 low for 140 usecs)
            if self.t1 == 0:
                print("ADB: looks like we got SRQ!")
            else:
                if (self.cycles - self.adb_cyc_cnt) >= 58:
                    print("ADB: Tlt completed")
                    self.adb_state = 7
                    self.adb_cyc_cnt = self.cycles
        elif self.adb_state == 7: # init data transfer
            if (self.adb_cmd & 0xC) == 0xC: # ADB Talk
                self.adb_state = 8
                self.adb_cyc_cnt = self.cycles
                print("ADB Talk started")
            elif (self.adb_cmd & 0xC) == 0x8: # ADB Listen
                print("ADB Listen not supported yet")
                self.adb_state = 0
            else:
                print("Unsupported ADB command 0x%01X" % self.adb_cmd)
                self.adb_state = 0
        elif self.adb_state == 8: # wait for start bit
            self.t1 = ((self.p1 >> 7) & 1) ^ 1
            if self.t1:
                if (self.cycles - self.adb_cyc_cnt) >= 46:
                    print("ADB Tlt timeout reached")
                    self.adb_state = 0
            else:
                print("Checking ADB start bit")
                self.adb_state = 9
                self.adb_next_state = 10
                self.adb_cyc_cnt = self.cycles
                self.adb_low_time = 0
                self.adb_high_time = 0
                self.adb_phase = 0 # low phase
        elif self.adb_state == 9: # receive one bit from device
            self.t1 = ((self.p1 >> 7) & 1) ^ 1 # inverse & copy port1:bit 7 to T1
            if self.t1 == 0:
                if self.adb_phase: # high-to-low transition
                    if (self.cycles - self.adb_cyc_cnt) < 15:
                        print("ADB timing error, high-to-low too short!")
                        self.adb_state = 0
                    else:
                        self.adb_high_time = (self.cycles - self.adb_cyc_cnt - self.adb_low_time)
                        # simple heuristic for distinguishing between 0 and 1 bist
                        # if the low phase is greater than 35 usecs, then assume
                        # we got a "0" bit, otherwise it's a "1" bit
                        if self.adb_low_time > 14:
                            self.adb_bit = 0
                        else:
                            self.adb_bit = 1
                        print("Got %d bit from ADB device" % self.adb_bit)
                        print("low duration: %f usecs" % (self.adb_low_time * 2.5))
                        print("high duration: %f usecs" % (self.adb_high_time * 2.5))
                        self.adb_state = self.adb_next_state
                        self.adb_cyc_cnt = self.cycles
                else:
                    if (self.cycles - self.adb_cyc_cnt) > 52:
                        print("ADB bit cell timeout 1 (greater than 130 usecs)")
                        self.adb_state = 0
                    else:
                        self.adb_low_time = (self.cycles - self.adb_cyc_cnt)
            else:
                if self.adb_phase == 0:
                    self.adb_low_time = (self.cycles - self.adb_cyc_cnt)
                    print("ADB line changed from low to high")
                self.adb_phase = 1
                self.adb_high_time = (self.cycles - self.adb_cyc_cnt - self.adb_low_time)
                if (self.cycles - self.adb_cyc_cnt) > 52:
                    print("ADB bit cell timeout 2 (greater than 130 usecs)")
                    self.adb_state = 0
        elif self.adb_state == 10: # check start bit
            if self.adb_bit == 0:
                print("Invalid ADB start bit. Aborting...")
                self.adb_state = 0
            else:
                self.adb_state = 9
                self.adb_next_state = 11
                self.adb_low_time = 0
                self.adb_high_time = 0
                self.adb_phase = 0 # always start with the low phase
                self.adb_bit_pos = 0
                self.adb_byte = 0
        elif self.adb_state == 11: # receive data from device
            if self.adb_bit_pos < 7:
                self.adb_byte = (self.adb_byte << 1) | self.adb_bit
                self.adb_bit_pos += 1
                self.adb_state = 9
                self.adb_next_state = 11
                self.adb_low_time = 0
                self.adb_high_time = 0
                self.adb_phase = 0 # always start with the low phase
            else:
                self.adb_byte = (self.adb_byte << 1) | self.adb_bit
                print("Got ADB byte 0x%01X from device" % self.adb_byte)
                self.adb_data.append(self.adb_byte)
                if len(self.adb_data) < 2:
                    self.adb_state = 9
                    self.adb_next_state = 11
                    self.adb_low_time = 0
                    self.adb_high_time = 0
                    self.adb_phase = 0 # always start with the low phase
                    self.adb_bit_pos = 0
                    self.adb_byte = 0
                else: # go receive stop bit
                    self.adb_state = 9
                    self.adb_next_state = 12
                    self.adb_cyc_cnt = self.cycles
                    self.adb_low_time = 0
                    self.adb_high_time = 0
                    self.adb_phase = 0 # always start with the low phase
        elif self.adb_state == 12:
            if self.adb_bit == 0:
                print("Received ADB stop bit. Stopping...")
            else:
                print("Invalid ADB stop bit. Stopping...")
            self.adb_state = 0

    def write_port(self, port, val):
        print("Port %d state changed to 0x%01X" % (port, val))
        if port == 1:
            self.p1 = val
        elif port == 2:
            self.p2 = val
        else:
            print("Unsupported port %d" % port)

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
            if self.adb_state:
                self.adb_transact()
            self.cycles += 1 # add extra cycle
            self.cond_jump(self.t1 ^ 1)
        elif opcode == 0x56: # JT1 addr
            if self.adb_state:
                self.adb_transact()
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

        # update ADB state machine
        if self.adb_state:
            self.adb_transact()
