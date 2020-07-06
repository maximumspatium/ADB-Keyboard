; Commented disassembly for the Apple Extended Keyboard II firmware
; that resides in the internal ROM of the 341-0731A chip.
;
; Author: Max Poliakovski 2020

    org     00000H

; -------------------------------------------------------------------------
; That's the place where the MCU will begin execution after RESET
; -------------------------------------------------------------------------
L0000:
    sel     mb0     ; select memory bank 0
    jmp     InitMCU

; -------------------------------------------------------------------------
; External interrupt service routine (never triggered)
; -------------------------------------------------------------------------
L0003:
    sel     mb0
    nop
    jmp     L0000

; -------------------------------------------------------------------------
; Timer/Counter interrupt service routine (never triggered)
; -------------------------------------------------------------------------
L0007:
    sel     mb0
    jmp     L0000

L000A:
    retr

; -------------------------------------------------------------------------
; MCU initialization code (L000B)
; -------------------------------------------------------------------------
InitMCU:
    ; configure all Port 2 lines as input
    ; That's what Intel manual says about that:
    ; Ports 1 and 2 are configured to allow input on a given pin
    ; by first writing a "1" out to the pin.
    orl     p2,#0FFH

    dis     i           ; disable external interrupts
    dis     tcnti       ; disable timer/counter interrupts
    stop    tcnt        ; stop timer/counter
    clr     f1          ; clear F1 flag
    call    L000A

    mov     a,#00FH     ; Configure Port 1 pins as follows: 0 - 3 for input
    outl    p1,a        ; pins 4-7 for output

    clr     a           ;
    mov     psw,a       ; write 0 to PSW (reset program stack)
    mov     t,a         ; write 0 to timer/counter

    ; zero RAM region 0x00 - 0x28
    ; this will initialize all registers and program stack with zeros
    mov     r0,#028H
L001B:
    mov     @r0,a
    djnz    r0,L001B

; -------------------------------------------------------------------------
; reset device's mode and flags to defaults (L001E)
; also called in response to ADB Reset
; -------------------------------------------------------------------------
ResetDevice:
    sel     rb1         ; select register bank 1

    mov     r6,#022H    ; lower nibble = device address = 2 (keyboard)
                        ; upper nibble = device control bits, bit 5: SRQ enable

    jni     L0027       ; is INT line pulled low?
    mov     r5,#002H    ; set device handler ID = 2 (standard keyboard)
    jmp     L0029       ; if INT is high
L0027:
    mov     r5,#005H    ; otherwise, set device handler ID = 5 (?)

L0029:
    mov     a,r7        ;
    anl     a,#07DH     ; clear bit 7 in rb1.R7 -> deactivate keyboard scanning
    mov     r7,a        ;

; -------------------------------------------------------------------------
; Flush device's pending events, reset internal state (L002D)
; also called in response to ADB Flush
; -------------------------------------------------------------------------
FlushEvents:
    sel     rb0         ; select register bank 0
    mov     r0,#026H    ;
    mov     @r0,#02CH   ; RAM + 0x26 = 0x2C
    inc     r0          ;
    mov     @r0,#030H   ; RAM + 0x27 = 0x30
    inc     r0          ;
    mov     @r0,#030H   ; RAM + 0x28 = 0x30
    inc     r0          ;
    mov     @r0,#04FH   ; RAM + 0x29 = 0x4F
    inc     r0          ;
    mov     @r0,#04FH   ; RAM + 0x2A = 0x4F
    inc     r0          ; r0 = RAM + 0x2B

    mov     a,#0FFH     ;
    movx    @r0,a       ; configure the bus port for input

    ; initialize memory region 0x2B - 0x7F to 0xFF
    mov     r1,#055H
L0044:
    mov     @r0,#0FFH
    inc     r0
    djnz    r1,L0044

    mov     r2,#011H    ; initialize keyscan loop counter
    clr     f1          ;
    cpl     f1          ; F1 = 1

; -------------------------------------------------------------------------
; Main loop (L004D) - scans the keyboard and monitors the ADB bus.
; The keyboard is scanned column wise, one column per iteration.
; Incoming ADB events will be checked after each column.
; Keyboard scanning is disabled during device reset.
; It will be enabled when a ADB command is sent to that device.
; -------------------------------------------------------------------------
MainLoop:
    en      tcnti       ; enable timer/counter interrupts
    strt    cnt         ; start T1 event counter
    sel     rb0         ; select register bank 0
    jt1     L0059       ; jump if ADB line is high (ADB idle)
    jf1     L005A       ; jump if F1 is set
    mov     a,t         ; a non-zero value of the counter means that there was
    jnz     L005B       ; a transition from high to low on the T1 pin,
                        ; proceed with next iteration then
    jmp     ProcessADB  ; otherwise, go process ADB event

L0059:
    clr     f1          ; F1 will be set
L005A:
    cpl     f1          ; flip F1
L005B:
    clr     a           ;
    mov     t,a         ; reset the timer/counter

    sel     rb1         ;
    mov     a,r7        ; is bit 7 of rb1.R7 set?
    sel     rb0         ;
    jb7     L0065       ; proceed with keyboard scanning if it's set
    inc     r7          ; otherwise, increment rb0.R7 used for random
                        ; address generation (see ADB Talk reg 3 command)

L0063:
    jmp     MainLoop

; -------------------------------------------------------------------------
; Dispatch keyboard scanning
L0065:
    dec     r2          ; decrement keyscan counter
    mov     a,r2        ;
    xrl     a,#0FFH     ;
    jnz     L006F       ; go if keyscan counter >= 0
    mov     r2,#011H    ; reset keyscan counter when it reaches 0xFF
    jmp     L0255       ;

L006F:
    mov     a,r2        ;
    xrl     a,#010H     ;
    jz      DoOption    ; go check modifier keys if keyscan counter = 0x10
    jmp     L0100       ; otherwise, go scan next column of alphanumeric keys

; -------------------------------------------------------------------------
; Scan the option keys and generate the corresponding scan codes (L0076)
; The right option is connected to the T0 pin (low - pressed, high - released)
; while the left option is a part of the modifiers set (Port 2)
; This routine distinguishes between right-hand and left-hand option keys and
; will generate different key codes for them if device handler ID is 3.
; Otherwise, it will generate the same code for both keys (standard mode).
; Pressing both option keys at the same time when in the standard mode
; will report only left-hand key presses.
; -------------------------------------------------------------------------
DoOption:
    sel     rb1         ; select register bank 1
    jnt0    L007E       ; go if the right-hand option key is pressed
    mov     a,r7        ; otherwise, check its previous state -> bit 3 of rb1.R7
    jb3     L0097       ; if this bit is set, go generate key release event
    jmp     ReadModKeys ; otherwise, proceed with scanning of modifier keys

L007E:
    mov     a,r7        ; check previous state of the right-hand option key
    jb3     ReadModKeys ; if it's 1, the key is still down, no further processing
    jt0     ReadModKeys ; go if the right-hand option key is released
    orl     a,#008H     ; otherwise, set bit 3 in rb1.R7
    mov     r7,a        ; (right option status: 1 = pressed)
    mov     a,r5        ;
    xrl     a,#003H     ; check device handler ID in rb1.R5
    jz      L0093       ; go if that ID = 3 (extended scan codes mode)
    in      a,p2        ; read modifier keys state
    cpl     a           ; skip event generation
    jb1     ReadModKeys ; if the left-hand option is also pressed
    mov     a,#03AH     ; otherwise, generate key-down event for option
    jmp     L00AB       ; (right/left option share the same scan code 0x3A)

L0093:
    mov     a,#07CH     ; generate separate key-down event for the right option
    jmp     L00AB       ; if device handler ID is 3

L0097:
    jnt0    ReadModKeys ; right-hand option pressed? -> skip event generation
    anl     a,#0F7H     ; clear bit 3 in rb1.R7
    mov     r7,a        ; (right option status: 0 = released)
    mov     a,r5        ;
    xrl     a,#003H     ; check device handler ID in rb1.R5
    jz      L00A9       ; go if that ID = 3 (extended scan codes mode)
    in      a,p2        ; read modifier keys state
    cpl     a           ; skip event generation
    jb1     ReadModKeys ; if the left-hand option is pressed
    mov     a,#0BAH     ; otherwise, generate key-up event for option
    jmp     L00AB       ; (right/left option share the same scan code 0x3A)

L00A9:
    mov     a,#0FCH     ; generate separate key-up event for the right option
                        ; if device handler ID is 3

L00AB:
    mov     r0,a        ;
    call    L0773       ; enqueue key event

; -------------------------------------------------------------------------
; Read status of the modifier keys and ensure
; it's is stable for at least 140 µs
; Modifiers state is stored in rb0.R4:
; - bit 0 : left/right command (P20, pin 21)
; - bit 1 : left option   (P21, pin 22)
; - bit 2 : left shift    (P22, pin 23)
; - bit 3 : left control  (P23, pin 24)
; - bit 4 : Power Switch  (P24, pin 35)
; - bit 5 : caps lock     (P25, pin 36)
; - bit 6 : right shift   (P26, pin 37)
; - bit 7 : right control (P27, pin 38)
; -------------------------------------------------------------------------
ReadModKeys:
    sel     rb0         ; select register bank 0
    mov     r1,#008H    ; loop counter
    in      a,p2        ; read modifier keys status
    mov     r4,a        ; and store it in rb0.R4

L00B3:
    in      a,p2        ; read modifiers again
    xrl     a,r4        ; state changed?
    jnz     ReadModKeys ; --> re-read and retry
    djnz    r1,L00B3    ; otherwise, continue checking
    jmp     L0102       ; go to event processing

; -------------------------------------------------------------------------
; Read status for alphanumeric keys (L00BB) and store it in rb0.R4
; rb0.R2 contains column number (0...F)
; -------------------------------------------------------------------------
ReadKeys:
    mov     a,#0FFH     ;
    movx    @r0,a       ; configure the bus port for input

    in      a,p1        ; get port 1 state
    anl     a,#0F0H     ; keep LED state and ADB out bits unchanged
    orl     a,r2        ; insert column number into the lower nibble
    outl    p1,a        ; update port 1 -> will select the corresponding column

L00C3:
    mov     r1,#008H    ; wait counter, 140 µs in total
    ins     a,bus       ; read key status for the current column
    mov     r4,a        ; and store it in rb0.R4

L00C7:
    ins     a,bus       ; read keys again
    xrl     a,r4        ; state changed?
    jnz     L00C3       ; --> re-read and retry
    djnz    r1,L00C7    ; otherwise, continue checking
    ret

; -------------------------------------------------------------------------
; Lookup table for converting key position (column/row) to scan code.
; Organized as 18 columns, 8 keys each.
; -------------------------------------------------------------------------
    org     00370H

    ; scan codes when in the standard keyboard mode (device handler ID 2)
    db      037H        ; left/right command
    db      03AH        ; left option
    db      038H        ; left shift
    db      036H        ; left control
    db      07FH        ; Power Switch
    db      039H        ; caps lock
    db      038H        ; right shift
    db      036H        ; right control

    ; scan codes when in the extended keyboard mode (device handler ID 3)
    db      037H        ; left/right command
    db      03AH        ; left option
    db      038H        ; left shift
    db      036H        ; left control
    db      07FH        ; Power Switch
    db      039H        ; caps lock
    db      07BH        ; right shift
    db      07DH        ; right control

    ; column 0
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      04CH        ; Keypad ENTER
    db      055H        ; Keypad "3"
    db      04EH        ; Keypad "-"
    db      043H        ; Keypad "*"
    db      04BH        ; Keypad "/"
    db      05CH        ; Keypad "9"

    ; column 1
    db      041H        ; Keypad "."
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      03CH        ; right arrow
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      051H        ; Keypad "="
    db      047H        ; Numlock/Clear

    ; column 2
    db      0FFH        ; unassigned
    db      045H        ; Keypad "+"
    db      056H        ; Keypad "4"
    db      057H        ; Keypad "5"
    db      058H        ; Keypad "6"
    db      059H        ; Keypad "7"
    db      05BH        ; Keypad "8"
    db      0FFH        ; unassigned

    ; column 3
    db      03DH        ; arrow down
    db      03BH        ; left arrow
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      071H        ; F15/Pause
    db      06BH        ; F14/Scroll Lock

    ; column 4
    db      054H        ; Keypad "2"
    db      0FFH        ; unassigned
    db      03EH        ; arrow up
    db      075H        ; del
    db      077H        ; end
    db      079H        ; Page Down
    db      074H        ; Page Up
    db      069H        ; F13/Print Screen

    ; column 5
    db      053H        ; Keypad "1"
    db      02FH        ; "."
    db      024H        ; return
    db      072H        ; help/ins
    db      073H        ; home
    db      02AH        ; \|
    db      033H        ; Delete
    db      06FH        ; F12

    ; column 6
    db      052H        ; Keypad "0"
    db      02CH        ; /?
    db      027H        ; "'
    db      01EH        ; ]}
    db      021H        ; [{
    db      018H        ; =+
    db      067H        ; F11
    db      06DH        ; F10

    ; column 7
    db      02EH        ; M
    db      02BH        ; ,<
    db      029H        ; ;:
    db      023H        ; P
    db      01BH        ; -_
    db      01FH        ; O
    db      01DH        ; 0)
    db      065H        ; F9

    ; column 8
    db      02DH        ; N
    db      026H        ; J
    db      025H        ; L
    db      028H        ; K
    db      0FFH        ; unassigned
    db      019H        ; 9(
    db      064H        ; F8
    db      062H        ; F7

    ; column 9
    db      0FFH        ; unassigned
    db      004H        ; H
    db      0FFH        ; unassigned
    db      022H        ; I
    db      0FFH        ; unassigned
    db      01CH        ; 8*
    db      01AH        ; 7&
    db      061H        ; F6

    ; column 10
    db      031H        ; Space
    db      00BH        ; B
    db      020H        ; U
    db      0FFH        ; unassigned
    db      010H        ; Y
    db      011H        ; T
    db      016H        ; 6^
    db      060H        ; F5

    ; column 11
    db      009H        ; V
    db      003H        ; F
    db      0FFH        ; unassigned
    db      00FH        ; R
    db      005H        ; G
    db      017H        ; 5%
    db      015H        ; 4$
    db      076H        ; F4

    ; column 12
    db      008H        ; C
    db      0FFH        ; unassigned
    db      002H        ; D
    db      00EH        ; E
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      014H        ; 3#
    db      063H        ; F3

    ; column 13
    db      007H        ; X
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      00DH        ; W
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      013H        ; 2@
    db      078H        ; F2

    ; column 14
    db      006H        ; Z
    db      001H        ; S
    db      0FFH        ; unassigned
    db      00CH        ; Q
    db      0FFH        ; unassigned
    db      0FFH        ; unassigned
    db      012H        ; 1!
    db      07AH        ; F1

    ; column 15
    db      0FFH        ; unassigned
    db      000H        ; A
    db      0FFH        ; unassigned
    db      030H        ; tab
    db      0FFH        ; unassigned
    db      00AH        ; <> (French and German keyboards)
    db      032H        ; `~
    db      035H        ; esc

; -------------------------------------------------------------------------
; Jump table for handling ADB commands.
; Each byte contains an offset within page 4 to the corresponding handler.
; -------------------------------------------------------------------------
    org     00400H

    db      020H        ; Send Reset,      jumps to L0420
    db      059H        ; Flush,           jumps to L0459
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      039H        ; invalid command, jumps to L0439
    db      0FBH        ; Listen reg 2,    jumps to L04FB
    db      057H        ; Listen Reg 3,    jumps to L0457
    db      05FH        ; Talk register 0, jumps to L045F
    db      039H        ; invalid command, jumps to L0439
    db      0A0H        ; Talk register 2, jumps to L04A0
    db      0DFH        ; Talk register 3, jumps to L04DF

; -------------------------------------------------------------------------
; Process incoming ADB messages (L0413).
; -------------------------------------------------------------------------
    org     00413H

ProcessADB:
    sel     rb1         ; select register bank 1
    mov     r1,#052H    ; loop counter

    ; the following busy waiting loop waits for the Attention
    ; signal to go from low to high within 820 µs.
    ; each instruction cycle takes 2.5 µs on 8048/8049
    ; jt1 and djnz require two cycles so 2.5 * 2 = 5 µs
    ; one iteration will take 10 µs, 82 * 10 = 820 µs in total
L0416:
    jt1     L0423       ; exit the loop if T1 is high
    djnz    r1,L0416    ; otherwise, keep waiting

    mov     r1,#088H    ; another busy waiting loop (136 * 10 = 1360 µs)
L041C:
    jt1     L0423       ; exit the loop if T1 is high
    djnz    r1,L041C    ; otherwise, keep waiting

    ; if we got here, the T1 line is still low and we're already waiting
    ; for 830 + 1360 = 2190 µs. The only ADB signal that is permitted
    ; to stay low for that long is ADB Reset.
L0420:
    nop
    jmp     ResetDevice

L0423:
    clr     f0          ; F0 = SRQ allowed = False
    mov     a,r6        ;
    swap    a           ; R3:upper nibble = my device address
    mov     r3,a        ; R3:lower nibble = my flags, bit 1: SRQ enable

    anl     a,r7        ; A = SRQ enable (R3:bit 1) & pending data (R7:bit 1)
    cpl     a           ; the device is allowed to generate SRQ
    jb1     L042C       ; if SRQ enable = 1 and there is data to send
    cpl     f0          ; SRQ allowed = True

L042C:
    mov     r1,#009H    ; number of bits in the 1st ADB byte (including Sync)
    mov     r0,#001H    ; number of bytes to receive
    call    ADBRcv1     ; receive ADB Command byte to A
    xrl     a,r3        ; process the received command if device address
    anl     a,#0F0H     ; in the upper nibble of the command byte matches
    jz      HandleCmd   ; our address
    jf0     GenSRQ      ; go generate SRQ if SRQ allowed is true

L0439:
    jmp     MainLoop    ; otherwise, return to the main loop

; -------------------------------------------------------------------------
; Generate service request (SRQ).
; This is accomplished by extending the low portion of the command stop bit
; by 140 µs.
; -------------------------------------------------------------------------
GenSRQ:
    orl     p1,#080H    ; pull ADB out low (inverse logic)
    mov     r1,#01CH    ; loop counter (28 * 2 = 56 cycles * 2.5 µs = 140 µs)

L043F:
    djnz    r1,L043F    ; busy waiting while holding the bus low
    anl     p1,#07FH    ; release the bus
    jmp     MainLoop

; -------------------------------------------------------------------------
; Proceed with handling the requested ADB Command.
; -------------------------------------------------------------------------
HandleCmd:
    mov     a,r7        ;
    orl     a,#080H     ; set bit 7 in rb1.R7 -> enable keyboard scanning
    mov     r7,a        ;

    ; busy waiting for ADB line to go from low to high within 350 µs
    ; (Stop-bit-to-start-bit time aka Tlt). That's because another
    ; device may generate SRQ.
    mov     r1,#023H    ; loop counter (35 * 4 = 140 cycles * 2.5 µs = 350 µs)
L044B:
    jt1     DispatchCmd ; exit the loop if T1 is high
    djnz    r1,L044B    ; otherwise, keep waiting
    jmp     MainLoop    ; start bit timeout, return to main loop

DispatchCmd:
    clr     a           ;
    mov     t,a         ; reset timer/counter (2 cycles)
    mov     a,r3        ; grab the lower nibble of the received ADB command
    anl     a,#00FH     ; (command + register)
    jmpp    @a          ; dispatch to the corresponding handler via table @ 0x400

; -------------------------------------------------------------------------
; Jump to the handler for Listen Reg 3 command.
; -------------------------------------------------------------------------
L0457:
    jmp     L051D       ; perform cross-segment jump

; -------------------------------------------------------------------------
; Handler for ADB Flush command.
; -------------------------------------------------------------------------
L0459:
    mov     a,r7
    anl     a,#0F5H
    mov     r7,a
    jmp     FlushEvents

; -------------------------------------------------------------------------
; Handler for ADB Talk Reg 0 command.
; -------------------------------------------------------------------------
L045F:
    mov     a,r7
    cpl     a
    jb1     L049E
    cpl     a
    anl     a,#0FEH
    mov     r7,a
    mov     r3,#0FFH
    mov     r0,#02AH
    mov     a,@r0
    mov     r0,a
    mov     a,@r0
    mov     r4,a
    xrl     a,#07FH
    anl     a,#07FH
    jnz     L047C
    mov     a,@r0
    orl     a,#07FH
    mov     r4,a
    mov     r3,a
    jmp     L0490

L047C:
    inc     r0
    mov     r1,#029H
    mov     a,@r1
    xrl     a,r0
    jz      L0490
    mov     a,@r0
    xrl     a,#07FH
    anl     a,#07FH
    jz      L0490
    mov     a,@r0
    mov     r3,a
    mov     a,r7
    orl     a,#001H
    mov     r7,a

L0490:
    mov     r1,#006H
    call    ADBXmit
    mov     r0,#02AH
    mov     a,r7
    cpl     a
    jb0     L049B
    inc     @r0

L049B:
    inc     @r0
    call    L0787

L049E:
    jmp     MainLoop

; -------------------------------------------------------------------------
; Handler for ADB Talk Reg 2 command.
;
; Implementation note: the device reads the statuses of the modifier
; keys and LEDs directly without consulting the events cache.
; -------------------------------------------------------------------------
L04A0:
    anl     p1,#0F0H    ; keep LED state and ADB out bits unchanged
    orl     p1,#001H    ; select column 1 using the lower nibble of the port 1
    ins     a,bus       ; read keys status for column 1
    anl     a,#080H     ; keep only Numlock/Clear status
    mov     r3,a        ; and put it into rb1.R3

    anl     p1,#0F0H    ; keep LED state and ADB out bits unchanged
    orl     p1,#003H    ; select column 3 using the lower nibble of the port 1
    ins     a,bus       ; read keys status for column 3
    rr      a           ;
    anl     a,#040H     ; isolate F14/Scroll Lock status bit
    orl     a,r3        ; and shift it into the bit position 6 of rb1.R3
    mov     r3,a        ;

    in      a,p1        ; read Port 1 status
    cpl     a           ; invert all its bits
    anl     a,#070H     ; isolate the LED status bits
    swap    a           ; and place them into bits 0-2 of rb1.R3
    orl     a,r3        ;

    orl     a,#038H     ; set unused bits of rb1.R3 (reg 2 LSB) to 1
    mov     r3,a        ;

    in      a,p2        ;
    jb7     L04C0       ;
    anl     a,#0F7H     ; clear bit 11 of reg 2 if right control is pressed

L04C0:
    orl     a,#080H     ; set bit 15 of reg 2 to 1
    jb6     L04C6       ;
    anl     a,#0BBH     ; clear bit 10 of reg 2 if right shift is pressed

L04C6:
    jt0     L04CA       ;
    anl     a,#0BDH     ; clear bit 9 of reg 2 if right option is pressed

L04CA:
    anl     a,#0BFH     ; clear bit 14 (Delete key status) of reg 2
    mov     r4,a        ;
    anl     p1,#0F0H    ; keep LED state and ADB out bits unchanged
    orl     p1,#005H    ; select column 5 using the lower nibble of the port 1
    ins     a,bus       ; read keys status for column 5
    cpl     a           ;
    jb6     L04D9       ; branch if Delete key is pressed
    mov     a,r4        ;
    orl     a,#040H     ; otherwise, set bit 14 of reg 2 (= Delete released)
    mov     r4,a        ;

L04D9:
    mov     r1,#002H    ; delay = 2 * 2 = 4 * 2.5 µs = 10 µs
    call    ADBXmit     ; send two bytes R4(MSB)/R3(LSB) to host over ADB
    jmp     MainLoop

; -----------------------------------------------------------------------------
; Handler for ADB Talk Reg 3 command.
;
; Important implementation detail not mentioned in the Apple ADB documentation:
; the device sends a random address in the bits 8-11 instead of its default
; address.
; This is a part of the ADB address conflict resolution process.
; For a detailed description please refer to Microchip Application Note AN591,
; "How Address Conflicts are Resolved".
;
; rb1.R6 - contains the MSB of the register 3 (bits 8-15)
; rb1.R5 - contains the LSB of the register 3 (bits 0-7)
; -----------------------------------------------------------------------------
L04DF:
    mov     a,r6        ;
    anl     a,#0F0H     ; put the upper nibble of the device reg 3 (MSB)
    mov     r4,a        ; into rb1.R4 (exceptional event bit, SRQ enable)
    sel     rb0         ;
    mov     a,r7        ; generate a random byte as follows:
    rl      a           ; rb0.R7 <<= 1
    mov     r7,a        ; (rb0.R7 will be incremented in the main loop)
    sel     rb1         ;
    anl     a,#00FH     ;
    orl     a,r4        ;
    mov     r4,a        ; put a random address into the lower nibble of rb1.R4
    in      a,p2        ; read modifier keys status
    anl     a,#010H     ; keep only the Power Switch bit (active low)
    rl      a           ;
    rl      a           ; shift it in the bit position 6
    orl     a,r4        ; put Power Switch state into the Exceptional event bit
    mov     r4,a        ; (bit 14 of register 3)
    mov     a,r5        ;
    mov     r3,a        ; rb1.R3 = current device handler ID
    mov     r1,#008H    ; delay => 8 * 2 = 16 * 2.5 µs = 40 µs
    call    ADBXmit     ; send two bytes R4(MSB)/R3(LSB) to host over ADB
    jmp     MainLoop

; -------------------------------------------------------------------------
; Handler for ADB Listen Reg 2 command.
;
; Updates only LEDs status bits.
; -------------------------------------------------------------------------
L04FB:
    jmp     L0500       ; cross-segment jump

    org     00500H

L0500:
    clr     a           ;
    mov     r3,a        ; clear reg2 MSB

    ; busy waiting for ADB data line to go from high to low within 260 µs
    mov     r1,#01AH    ; loop counter = 26 * 4 = 104 cycles * 2.5 µs = 260 µs
L0504:
    jnt1    L050A       ; exit the loop if T1 is low
    djnz    r1,L0504    ; otherwise, keep waiting
    jmp     MainLoop    ; start bit timeout reached, return to main loop

L050A:
    mov     r1,#009H    ; number of bits in the 1st ADB byte (including Sync)
    mov     r0,#002H    ; number of bytes to receive
    call    ADBRcv      ; receive two bytes from host
    mov     a,r3        ; get the LSB of the received reg2 value
    swap    a           ;
    cpl     a           ; extract the LEDs status bits (lower nibble)
    anl     a,#070H     ; and move them to the upper nibble
    mov     r2,a        ; of rb1.R2
    in      a,p1        ; read Port 1 status
    anl     a,#08FH     ; keep all bits expect LEDs bits unchanged
    orl     a,r2        ; add new LEDs status bits
    outl    p1,a        ; update Port 1
    jmp     MainLoop

; -------------------------------------------------------------------------
; Handler for ADB Listen Reg 3 command.
; -------------------------------------------------------------------------
L051D:
    clr     a           ;
    mov     r4,a        ; clear rb1.R3 and rb1.R4 that will hold
    mov     r3,a        ; ADB bytes received from host

    ; busy waiting for ADB data line to go from high to low within 260 µs
    mov     r1,#01AH    ; loop counter = 26 * 4 = 104 cycles * 2.5 µs = 260 µs
L0522:
    jnt1    L0529       ; exit the loop if T1 is low
    djnz    r1,L0522    ; otherwise, keep waiting
    jmp     MainLoop    ; start bit timeout reached, return to main loop
    nop

L0529:
    mov     r1,#009H    ; number of bits in the 1st ADB byte (including Sync)
    mov     r0,#002H    ; number of bytes to receive
    call    ADBRcv      ; receive two bytes from host
    mov     r4,a        ; rb1.R4 contains the MSB of the received value

    mov     a,r3        ; rb1.R3 contains the LSB of the received value
    jnz     L0539       ; --> new device handler ID, branch if it's non-zero
    mov     a,r4        ; otherwise, copy the MSB value into rb1.R6
    anl     a,#02FH     ; that contains new device address and SRQ enable flag
    mov     r6,a        ;

L0537:
    jmp     MainLoop    ; done

L0539:
    xrl     a,#0FFH     ; if device handler ID = 0xFF (Self-Test mode)
    jnz     L053F       ;
    jmp     L0459       ; go and flush internal event cache (equivalent to ADB Flush)

L053F:
    xrl     a,#002H     ;
    jnz     L0550       ; branch if device handler ID ≠ 0xFD
    in      a,p2        ; check for activator key --> left/right command
    jb0     L0537       ; done if the activator key isn't pressed

    ; perform address change if device activator key is pressed
L0546:
    mov     a,r4        ; grab new device address from rb1.R4
    anl     a,#00FH     ;
    xch     a,r6        ; and put it into the lower nibble of rb1.R6
    anl     a,#020H     ; grab new SRQ enable bit value
    orl     a,r6        ; and put it into bit 5 of rb1.R6
    mov     r6,a        ;
    jmp     MainLoop

    ; perform address change if no collision detected
L0550:
    xrl     a,#003H     ;
    jnz     L0559       ; branch if device handler ID ≠ 0xFE
    mov     a,r7        ; otherwise, check the "collision" bit (rb1.R7:2)
    jb2     L0537       ; if there was a collision, we're done
    jmp     L0546       ; otherwise, go and accept new device address

L0559:
    mov     a,r3        ;
    xrl     a,#003H     ;
    jz      L0568       ; branch if device handler ID = 3
    mov     a,r3        ;
    xrl     a,#002H     ;
    jz      L0568       ; branch if device handler ID = 2
    mov     a,r3        ;
    xrl     a,#005H     ;
    jnz     L0537       ; if device handler ID ≠ 5, ignore the unknown ID value

L0568:
    mov     a,r3        ;
    mov     r5,a        ; store new device handler ID in rb1.R5
    jmp     MainLoop

; -------------------------------------------------------------------------
; Transmit a 16bit value over the ADB bus.
; rb1.R4 contains the MSB, rb1.R3 the LSB of that value.
; The MSB will be sent first followed by the LSB.
; rb1.R1 contains the amount of an additional delay (n * 5 µs)
; before starting the transaction.
; The routine will continually check for ADB idle signal (T1 high)
; and abort immediatedly with collision bit set if the ADB line goes low
; unexpectedly.
; -------------------------------------------------------------------------
ADBXmit:
    mov     a,r7        ;
    orl     a,#004H     ; set the "collision" bit in rb1.R7
    mov     r7,a        ;

    mov     r0,#008H    ; bits counter

L0572:
    djnz    r1,L0572    ; perfom the requested delay (n * 5 µs)

    mov     a,t         ; a non-zero value of the timer/counter means that
    jnz     AbortXmit   ; another device has pulled the line low -> abort
                        ; transaction with collision bit set

    ; send ADB data start bit (35 µs low + 65 µs high)
    orl     p1,#080H    ; pull the ADB line low
    clr     a           ;
    mov     t,a         ; reset ADB line pulses counter
    call    Delay3      ;
    anl     p1,#07FH    ; release the ADB line
    nop                 ;
    jnt1    AbortXmit   ; ADB line low? --> abort with collision bit set
    call    Delay2      ;

L0584:
    jnt1    AbortXmit   ; ADB line low? --> abort with collision bit set
    call    Delay5      ;
    mov     a,t         ; "unauthorized" transition from high to low occured?
    jnz     AbortXmit   ; --> abort with collision bit set
    orl     p1,#080H    ; pull the ADB line low
    clr     a           ;
    mov     t,a         ; reset ADB line pulses counter
    call    Delay5      ;
    mov     a,r4        ;
    rl      a           ;
    mov     r4,a        ;
    jb0     L05CA       ; branch if the next bit to send is a "1" bit
    call    Delay1      ;
    anl     p1,#07FH    ; release the ADB line

L059A:
    djnz    r0,L0584    ; go transmit next bit
    jnt1    AbortXmit   ; ADB line low? --> abort with collision bit set
    mov     r0,#008H    ; otherwise, re-init the bits counter
    jmp     L05A6       ; go send the LSB

L05A2:
    jnt1    AbortXmit   ; ADB line low? --> abort with collision bit set
    call    Delay6      ;

L05A6:
    nop                 ;
    mov     a,t         ; "unauthorized" transition from high to low occured?
    jnz     AbortXmit   ; --> abort with collision bit set
    orl     p1,#080H    ; pull the ADB line low
    clr     a           ;
    mov     t,a         ; reset ADB line pulses counter
    call    Delay5      ;
    mov     a,r3        ;
    rl      a           ;
    mov     r3,a        ;
    jb0     L05D3       ; branch if the next bit to send is a "1" bit
    call    Delay1      ;
    anl     p1,#07FH    ; release the ADB line

L05B9:
    djnz    r0,L05A2    ; go transmit next bit
    call    Delay3      ;

    ; generate ADB data stop bit (65 µs low + 35 µs high)
    orl     p1,#080H    ; pull the ADB line low
    call    Delay1      ;
    call    Delay1      ; wait for 60 µs
    anl     p1,#07FH    ; then release the ADB line

    mov     a,r7        ; everything went well
    anl     a,#0FBH     ; --> clear the "collision" bit
    mov     r7,a        ;
    ret

    ; "1" bit path for MSB send
L05CA:
    anl     p1,#07FH    ; release the ADB line
    nop                 ;
    jnt1    AbortXmit   ; ADB line low? --> abort with collision bit set
    call    Delay4      ;
    jmp     L059A       ; go send next bit

    ; "1" bit path for LSB send
L05D3:
    anl     p1,#07FH    ; release the ADB line
    nop                 ;
    jnt1    AbortXmit   ; ADB line low? --> abort with collision bit set
    call    Delay4      ;
    jmp     L05B9       ; go send next bit

AbortXmit:
    clr     a           ;
    mov     psw,a       ; clear program stack
    jmp     MainLoop    ; return to main loop

Delay1: ; delay for 30 µs
    nop
Delay2: ; delay for 27.5 µs
    nop
Delay3: ; delay for 25 µs
    nop
    nop
    nop
Delay4: ; delay for 17.5 µs
    nop
    nop
Delay5: ; delay for 12.5 µs
    nop
Delay6: ; delay for 10 µs
    ret

; -------------------------------------------------------------------------
; Receive up to two bytes over the ADB bus.
; Params:
; rb1.R1 - number of bits in the first byte (to ensure the proper sync)
; rb1.R0 - number of bytes to receive, valid values are 1 and 2
; Result is returned as follows:
; one byte  message -> A
; two bytes message -> A = MSB, rb1.R3 - LSB
; -------------------------------------------------------------------------
    org     00600H

ADBRcv:
    clr     c           ; next bit is assumed to be "0" for now

    ; unrolled loop that waits for the ADB line to go high (timeout after 80 µs)
    jt1     L0641
    jt1     L063F
    jt1     L063D
    jt1     L063B
    jt1     L0639
    jt1     L0637
    jt1     L0635
    jt1     L0633
    jt1     L0631
    jt1     L062F
    jt1     L062D
    jt1     L062B
    jt1     L0629
    jt1     L0627
    jt1     L0625
    jt1     ADBRcv1
    jmp     AbortRcv ; timeout reached --> abort the transaction

    ; unrolled loop that waits for the ADB line to go low
    ; the following jumps are chained together so that the correct bit cell
    ; timing including the allowed tolerance is obeyed.
ADBRcv1:
    jnt1    L066C
L0625:
    jnt1    L066C
L0627:
    jnt1    L066C
L0629:
    jnt1    L066C
L062B:
    jnt1    L066C
L062D:
    jnt1    L066C
L062F:
    jnt1    L066C
L0631:
    jnt1    L066C
L0633:
    jnt1    L066C
L0635:
    jnt1    L066C
L0637:
    jnt1    L066C
L0639:
    jnt1    L066C
L063B:
    jnt1    L066C
L063D:
    jnt1    L066C
L063F:
    jnt1    L066C

L0641:
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C

    cpl     c           ; from now on, next bit will be a "1" bit

    ; unrolled loop that waits for the ADB line to go low (timeout after 80 µs)
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jnt1    L066C
    jmp     AbortRcv    ; timeout reached --> abort the transaction

L066C:
    rlc     a           ; shift carry (next bit) into the bit position 0 of A
    djnz    r1,ADBRcv   ; go receive next bit
    xch     a,r3        ; just received byte goes to rb1.R3, previous one to A
    djnz    r0,L0673    ; go receive 2nd byte
    ret

L0673:
    mov     r1,#008H    ; init bits counter

    clr     c           ; next bit is assumed to be "0" for now

    ; unrolled loop that waits for the ADB line to go high (timeout after 80 µs)
    jt1     L063D
    jt1     L063B
    jt1     L0639
    jt1     L0637
    jt1     L0635
    jt1     L0633
    jt1     L0631
    jt1     L062F
    jt1     L062D
    jt1     L062B
    jt1     L0629
    jt1     L0627
    jt1     L0625
    jt1     ADBRcv1

AbortRcv:
    jmp     AbortXmit
