# Supported save files

| Extension | Source | When is it detected? |
| --- | --- | --- |
| .sav | EverDrive, DS flash cards, TWiLight Menu++ | everywhere |
| .srm | SD2SNES / FXPak Pro, RetroArch | everywhere |
| .bin | Checkpoint (3DS), JKSV (Switch) | only inside Checkpoint/JKSV folders |
| .eep / .sra / .fla | EverDrive 64 | only inside ED-64 folders |
| main | Checkpoint (3DS) | only inside Checkpoint folders |

Files are recognised by extension first, then filtered by context folder and
size. Everything else on the card is left untouched.
