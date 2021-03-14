'''
    Emulator for the Apple Desktop Bus (ADB).

    Author: Max Poliakovski 2020-2021.
'''

# ADB FSM states
ADB_STATE_IDLE     = 0 # no ADB transaction in progress
ADB_STATE_START    = 1
ADB_STATE_ATT      = 2
ADB_STATE_SYNC     = 3
ADB_STATE_SEND_CMD = 4
ADB_STATE_STOP     = 5
ADB_STATE_TLT      = 6
ADB_STATE_DATA     = 7

class ADBSim:
    def __init__(self, cpu_obj):
        self.cpu_obj = cpu_obj
        self.adb_state = ADB_STATE_IDLE
        self.adb_next_state = ADB_STATE_IDLE
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
        self.cpu_obj.set_t1_line(1) # pull ADB-out line high (ADB idle)
        self.adb_in_cb = None
        self.adb_in_mask = 0x80
        print("ADB bus sucessfully initialized...")

    def adb_send(self, adb_cmd):
        self.adb_cmd = adb_cmd
        self.adb_data = bytearray()
        self.adb_state = ADB_STATE_START

    def set_adb_in_line(self, cb, mask):
        self.adb_in_cb = cb
        self.adb_in_mask = mask

    def _read_adb_in(self):
        if self.adb_in_cb:
            return (self.adb_in_cb() & self.adb_in_mask) != 0

    def adb_transact(self, cycles):
        if self.adb_state == ADB_STATE_START: # start ADB transaction
            print("ADB transaction start")
            self.adb_cyc_cnt = cycles
            self.cpu_obj.set_t1_line(0) # pull ADB-in line low
            self.adb_state = ADB_STATE_ATT
        elif self.adb_state == ADB_STATE_ATT:
            # generate attention (T1 low for 800 usecs)
            if (cycles - self.adb_cyc_cnt) >= 320:
                print("ADB attention ended")
                self.adb_cyc_cnt = cycles
                self.cpu_obj.set_t1_line(1) # pull ADB-in line high
                self.adb_state = ADB_STATE_SYNC
        elif self.adb_state == ADB_STATE_SYNC: # Sync (T1 high for 70 usecs)
            if (cycles - self.adb_cyc_cnt) >= 28:
                print("ADB Sync ended")
                self.adb_bit = 7
                self.adb_cyc_cnt = cycles
                self.cpu_obj.set_t1_line(0) # each bit cell starts low
                self.adb_state = ADB_STATE_SEND_CMD
        elif self.adb_state == ADB_STATE_SEND_CMD: # send command byte
            if self.adb_bit >= 0:
                if (cycles - self.adb_cyc_cnt) < 40: # 100 usecs cells
                    if (self.adb_cmd & (1 << self.adb_bit)): # bit=1
                        if (cycles - self.adb_cyc_cnt) >= 14:
                            self.cpu_obj.set_t1_line(1) # go high after 35 usecs
                    else: # bit=0
                        if (cycles - self.adb_cyc_cnt) >= 26:
                            self.cpu_obj.set_t1_line(1) # go high after 65 usecs
                else:
                    print("Sending next ADB bit")
                    self.cpu_obj.set_t1_line(0) # each bit cell starts low
                    self.adb_bit -= 1
                    if self.adb_bit < 0:
                        print("Sending ADB byte completed")
                        print("Sending STOP bit")
                        self.adb_state = ADB_STATE_STOP
                    self.adb_cyc_cnt = cycles
            else:
                print("ADB command byte already completed")
                self.adb_state = ADB_STATE_IDLE # abort transaction
        elif self.adb_state == ADB_STATE_STOP: # stop bit
            if (cycles - self.adb_cyc_cnt) >= 28:
                self.cpu_obj.set_t1_line(1) # go high after 70 usecs
                print("ADB stop bit completed")
                self.adb_cyc_cnt = cycles
                self.adb_state = ADB_STATE_TLT
        elif self.adb_state == ADB_STATE_TLT: # Tlt (T1 low for 140 usecs)
            if self.cpu_obj.get_t1_line() == 0:
                print("ADB: looks like we got a SRQ!")
            else:
                if (cycles - self.adb_cyc_cnt) >= 58:
                    print("ADB: Tlt completed")
                    self.adb_state = ADB_STATE_DATA
                    self.adb_cyc_cnt = cycles
        elif self.adb_state == ADB_STATE_DATA: # init data transfer
            if (self.adb_cmd & 0xC) == 0xC: # ADB Talk
                self.adb_state = 8
                self.adb_cyc_cnt = cycles
                print("ADB Talk started")
            elif (self.adb_cmd & 0xC) == 0x8: # ADB Listen
                print("ADB Listen not supported yet")
                self.adb_state = ADB_STATE_IDLE
            else:
                print("Unsupported ADB command 0x%01X" % self.adb_cmd)
                self.adb_state = ADB_STATE_IDLE
        elif self.adb_state == 8: # wait for start bit
            self.cpu_obj.set_t1_line(self._read_adb_in() ^ 1)
            if self.cpu_obj.get_t1_line():
                if (cycles - self.adb_cyc_cnt) >= 46:
                    print("ADB Tlt timeout reached")
                    self.adb_state = ADB_STATE_IDLE
            else:
                print("Checking ADB start bit")
                self.adb_state = 9
                self.adb_next_state = 10
                self.adb_cyc_cnt = cycles
                self.adb_low_time = 0
                self.adb_high_time = 0
                self.adb_phase = 0 # low phase
        elif self.adb_state == 9: # receive one bit from device
            self.cpu_obj.set_t1_line(self._read_adb_in() ^ 1)
            if self.cpu_obj.get_t1_line() == 0:
                if self.adb_phase: # high-to-low transition
                    if (cycles - self.adb_cyc_cnt) < 15:
                        print("ADB timing error, high-to-low too short!")
                        self.adb_state = ADB_STATE_IDLE
                    else:
                        self.adb_high_time = (cycles - self.adb_cyc_cnt - self.adb_low_time)
                        # simple heuristic for distinguishing between 0 and 1 bits
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
                        self.adb_cyc_cnt = cycles
                else:
                    if (cycles - self.adb_cyc_cnt) > 52:
                        print("ADB bit cell timeout 1 (greater than 130 usecs)")
                        self.adb_state = ADB_STATE_IDLE
                    else:
                        self.adb_low_time = (cycles - self.adb_cyc_cnt)
            else:
                if self.adb_phase == 0:
                    self.adb_low_time = (cycles - self.adb_cyc_cnt)
                    print("ADB line changed from low to high")
                self.adb_phase = 1
                self.adb_high_time = (cycles - self.adb_cyc_cnt - self.adb_low_time)
                if (cycles - self.adb_cyc_cnt) > 52:
                    print("ADB bit cell timeout 2 (greater than 130 usecs)")
                    self.adb_state = ADB_STATE_IDLE
        elif self.adb_state == 10: # check start bit
            if self.adb_bit == 0:
                print("Invalid ADB start bit. Aborting...")
                self.adb_state = ADB_STATE_IDLE
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
                    self.adb_cyc_cnt = cycles
                    self.adb_low_time = 0
                    self.adb_high_time = 0
                    self.adb_phase = 0 # always start with the low phase
        elif self.adb_state == 12:
            if self.adb_bit == 0:
                print("Received ADB stop bit. Stopping...")
            else:
                print("Invalid ADB stop bit. Stopping...")
            self.adb_state = ADB_STATE_IDLE
