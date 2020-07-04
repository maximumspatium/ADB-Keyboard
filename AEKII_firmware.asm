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

    mov     r6,#022H    ; upper nibble = device address = 2 (keyboard)
                        ; lower nibble = device control bits, bit 1: SRQ enable

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
    jmp     L0413       ; otherwise, go process ADB event

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
    inc     r7          ; otherwise, increment rb0.R7 (idle counter?)

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
    db      00AH        ; ??????????
    db      032H        ; `~
    db      035H        ; esc
