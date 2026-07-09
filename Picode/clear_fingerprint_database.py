from pyfingerprint.pyfingerprint import PyFingerprint

f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)

if f.verifyPassword():
    print("Clearing sensor database...")
    f.clearDatabase()
    print("All fingerprints deleted successfully.")
