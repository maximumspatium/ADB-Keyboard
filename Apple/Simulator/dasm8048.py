'''
    Very simple, standalone disassembler for the Intel MSC-48 instruction set.

    It recognizes all instructions defined in this architecture.

    The simplistic API consists of just three methods:
     - dasm_single()
     - set_uppercase()
     - set_opcode_width()

    Author: Max Poliakovski 2021
'''

class Dasm8048:
    def __init__(self):
        self.uppercase = False
        self.opc_width = 8

    def set_uppercase(self, flag):
        ''' Controls letter case of the output disassmbly:
            0 - lowercase, 1 - uppercase
        '''
        self.uppercase = flag

    def set_opcode_width(self, width):
        ''' Allows changing the width of the opcode field.
        '''
        self.opc_width = width

    def _fmt_instr(self, opc, ops):
        if self.uppercase:
            return (opc.ljust(self.opc_width) + ops).upper()
        else:
            return opc.ljust(self.opc_width) + ops

    def _fmt_imm(self, n):
        return '#' + '{0:03x}'.format(n) + 'h'

    def dasm_single(self, pc, bin):
        '''Disassemble single instruction.
           IN: pc  - current PC value,
               bin - data to disassemble, max. 2 bytes
           OUT: tuple(disassembly string, instruction length in bytes)
        '''
        opcode = bin[0]

        if opcode == 0x0:
            return (self._fmt_instr("nop", ""), 1)
        elif opcode == 0x2:
            return (self._fmt_instr("outl", "bus,a"), 1)
        elif opcode == 0x3:
            return (self._fmt_instr("add", 'a,' + self._fmt_imm(bin[1])), 2)
        elif (opcode & 0x1F) == 4:
            dest = ((opcode & 0xE0) << 3) | bin[1]
            return (self._fmt_instr("jmp", self._fmt_imm(dest)), 2)
        elif opcode == 0x05:
            return (self._fmt_instr("en", "i"), 1)
        elif opcode == 0x7:
            return (self._fmt_instr("dec", "a"), 1)
        elif (opcode & 0xFC) == 0x8:
            port = opcode & 3
            if port == 0:
                return (self._fmt_instr("ins", "a,bus"), 1)
            elif port == 1:
                return (self._fmt_instr("in", "a,p1"), 1)
            elif port == 2:
                return (self._fmt_instr("in", "a,p2"), 1)
        elif (opcode & 0xFC) == 0x0C:
            return (self._fmt_instr("movd", "a,p" + str((opcode & 3) + 4)), 1)
        elif (opcode & 0xFE) == 0x10:
            return (self._fmt_instr("inc", "@r" + str(opcode & 1)), 1)
        elif (opcode & 0x1F) == 0x12:
            bit_num = (opcode >> 5) & 7;
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jb" + str(bit_num), self._fmt_imm(dest)), 2)
        elif opcode == 0x13:
            return (self._fmt_instr("addc", "a," + self._fmt_imm(bin[1])), 2)
        elif (opcode & 0x1F) == 0x14:
            dest = ((opcode & 0xE0) << 3) | bin[1]
            return (self._fmt_instr("call", self._fmt_imm(dest)), 2)
        elif opcode == 0x15:
            return (self._fmt_instr("dis", "i"), 1)
        elif opcode == 0x16:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jtf", self._fmt_imm(dest)), 2)
        elif opcode == 0x17:
            return (self._fmt_instr("inc", "a"), 1)
        elif (opcode & 0xF8) == 0x18:
            return (self._fmt_instr("inc", "r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0x20:
            return (self._fmt_instr("xch", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x23:
            return (self._fmt_instr("mov", "a," + self._fmt_imm(bin[1])), 2)
        elif opcode == 0x25:
            return (self._fmt_instr("en", "tcnti"), 1)
        elif opcode == 0x26:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jnt0", self._fmt_imm(dest)), 2)
        elif opcode == 0x27:
            return (self._fmt_instr("clr", "a"), 1)
        elif (opcode & 0xF8) == 0x28:
            return (self._fmt_instr("xch", "a,r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0x30:
            return (self._fmt_instr("xchd", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x35:
            return (self._fmt_instr("dis", "tcnti"), 1)
        elif opcode == 0x36:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jt0", self._fmt_imm(dest)), 2)
        elif opcode == 0x37:
            return (self._fmt_instr("cpl", "a"), 1)
        elif (opcode & 0xFC) == 0x38:
            port_num = opcode & 3
            if port_num == 1 or port_num == 2:
                return (self._fmt_instr("outl", "p" + str(port_num) + ",a"), 1)
        elif (opcode & 0xFC) == 0x3C:
            return (self._fmt_instr("movd", "p" + str((opcode & 3) + 4) + ",a"), 1)
        elif (opcode & 0xFE) == 0x40:
            return (self._fmt_instr("orl", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x42:
            return (self._fmt_instr("mov", "a,t"), 1)
        elif opcode == 0x43:
            return (self._fmt_instr("orl", 'a,' + self._fmt_imm(bin[1])), 2)
        elif opcode == 0x45:
            return (self._fmt_instr("strt", "cnt"), 1)
        elif opcode == 0x46:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jnt1", self._fmt_imm(dest)), 2)
        elif opcode == 0x47:
            return (self._fmt_instr("swap", "a"), 1)
        elif (opcode & 0xF8) == 0x48:
            return (self._fmt_instr("orl", "a,r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0x50:
            return (self._fmt_instr("anl", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x53:
            return (self._fmt_instr("anl", 'a,' + self._fmt_imm(bin[1])), 2)
        elif opcode == 0x55:
            return (self._fmt_instr("strt", "t"), 1)
        elif opcode == 0x56:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jt1", self._fmt_imm(dest)), 2)
        elif opcode == 0x57:
            return (self._fmt_instr("da", "a"), 1)
        elif (opcode & 0xF8) == 0x58:
            return (self._fmt_instr("anl", "a,r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0x60:
            return (self._fmt_instr("add", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x62:
            return (self._fmt_instr("mov", "t,a"), 1)
        elif opcode == 0x65:
            return (self._fmt_instr("stop", "tcnt"), 1)
        elif opcode == 0x67:
            return (self._fmt_instr("rrc", "a"), 1)
        elif (opcode & 0xF8) == 0x68:
            return (self._fmt_instr("add", "a,r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0x70:
            return (self._fmt_instr("addc", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x75:
            return (self._fmt_instr("ent0", "clk"), 1)
        elif opcode == 0x76:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jf1", self._fmt_imm(dest)), 2)
        elif opcode == 0x77:
            return (self._fmt_instr("rr", "a"), 1)
        elif (opcode & 0xF8) == 0x78:
            return (self._fmt_instr("addc", "a,r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0x80:
            return (self._fmt_instr("movx", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0x83:
            return (self._fmt_instr("ret"), 1)
        elif opcode == 0x85:
            return (self._fmt_instr("clr", "f0"), 1)
        elif opcode == 0x86:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jni", self._fmt_imm(dest)), 2)
        elif (opcode & 0xFC) == 0x88:
            port_num = opcode & 3
            if port_num == 0:
                return (self._fmt_instr("orl", "bus," + self._fmt_imm(bin[1])), 1)
            elif port_num == 1 or port_num == 2:
                return (self._fmt_instr("orl", "p" +
                    str(port_num) + "," + self._fmt_imm(bin[1])), 2)
        elif (opcode & 0xFC) == 0x8C:
            return (self._fmt_instr("orld", "p" + str((opcode & 3) + 4) + ",a"), 1)
        elif (opcode & 0xFE) == 0x90:
            return (self._fmt_instr("movx", "@r" + str(opcode & 1) + ",a"), 1)
        elif opcode == 0x93:
            return (self._fmt_instr("retr"), 1)
        elif opcode == 0x95:
            return (self._fmt_instr("cpl", "f0"), 1)
        elif opcode == 0x96:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jnz", self._fmt_imm(dest)), 2)
        elif opcode == 0x97:
            return (self._fmt_instr("clr", "c"), 1)
        elif (opcode & 0xFC) == 0x98:
            port_num = opcode & 3
            if port_num == 0:
                return (self._fmt_instr("anl", "bus," + self._fmt_imm(bin[1])), 1)
            elif port_num == 1 or port_num == 2:
                return (self._fmt_instr("anl", "p" +
                    str(port_num) + "," + self._fmt_imm(bin[1])), 2)
        elif (opcode & 0xFC) == 0x9C:
            return (self._fmt_instr("anld", "p" + str((opcode & 3) + 4) + ",a"), 1)
        elif (opcode & 0xFE) == 0xA0:
            return (self._fmt_instr("mov", "@r" + str(opcode & 1) + ",a"), 1)
        elif opcode == 0xA3:
            return (self._fmt_instr("movp", "a,@a"), 1)
        elif opcode == 0xA5:
            return (self._fmt_instr("clr", "f1"), 1)
        elif opcode == 0xA7:
            return (self._fmt_instr("cpl", "c"), 1)
        elif (opcode & 0xF8) == 0xA8:
            return (self._fmt_instr("mov", "r" + str(opcode & 7) + ",a"), 1)
        elif (opcode & 0xFE) == 0xB0:
            return (self._fmt_instr("mov", "@r" + str(opcode & 1)
                + "," + self._fmt_imm(bin[1])), 2)
        elif opcode == 0xB3:
            return (self._fmt_instr("jmpp", "@a"), 1)
        elif opcode == 0xB5:
            return (self._fmt_instr("cpl", "f1"), 1)
        elif opcode == 0xB6:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jf0", self._fmt_imm(dest)), 2)
        elif (opcode & 0xF8) == 0xB8:
            return (self._fmt_instr("mov", "r" + str(opcode & 7)
                + "," + self._fmt_imm(bin[1])), 2)
        elif opcode == 0xC5:
            return (self._fmt_instr("sel", "rb0"), 1)
        elif opcode == 0xC6:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jz", self._fmt_imm(dest)), 2)
        elif opcode == 0xC7:
            return (self._fmt_instr("mov", "a,psw"), 1)
        elif (opcode & 0xF8) == 0xC8:
            return (self._fmt_instr("dec", "r" + str(opcode & 7)), 1)
        elif (opcode & 0xFE) == 0xD0:
            return (self._fmt_instr("xrl", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0xD3:
            return (self._fmt_instr("xrl", 'a,' + self._fmt_imm(bin[1])), 2)
        elif opcode == 0xD5:
            return (self._fmt_instr("sel", "rb1"), 1)
        elif opcode == 0xD7:
            return (self._fmt_instr("mov", "psw,a"), 1)
        elif (opcode & 0xF8) == 0xD8:
            return (self._fmt_instr("xrl", "a,r" + str(opcode & 7)), 1)
        elif opcode == 0xE3:
            return (self._fmt_instr("movp3", "a,@a"), 1)
        elif opcode == 0xE5:
            return (self._fmt_instr("sel", "mb0"), 1)
        elif opcode == 0xE6:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jnc", self._fmt_imm(dest)), 2)
        elif opcode == 0xE7:
            return (self._fmt_instr("rl", "a"), 1)
        elif opcode == 0xF5:
            return (self._fmt_instr("sel", "mb1"), 1)
        elif opcode == 0xF7:
            return (self._fmt_instr("rlc", "a"), 1)
        elif (opcode & 0xF8) == 0xE8:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("djnz", "r" + str(opcode & 7) + ","
                + self._fmt_imm(dest)), 2)
        elif (opcode & 0xFE) == 0xF0:
            return (self._fmt_instr("mov", "a,@r" + str(opcode & 1)), 1)
        elif opcode == 0xF6:
            dest = (pc & ~0xFF) | bin[1]
            return (self._fmt_instr("jc", self._fmt_imm(dest)), 2)
        elif (opcode & 0xF8) == 0xF8:
            return (self._fmt_instr("mov", "a,r" + str(opcode & 7)), 1)

        return ("unknown", 1)
