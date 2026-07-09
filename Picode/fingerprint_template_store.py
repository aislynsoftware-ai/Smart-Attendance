from pyfingerprint.pyfingerprint import PyFingerprint
import base64
import time

def enroll_fingerprint():

    try:
        f = PyFingerprint('/dev/serial0', 57600, 0xFFFFFFFF, 0x00000000)

        if not f.verifyPassword():
            raise ValueError('Sensor password incorrect')

        print("Place finger...")

        while not f.readImage():
            pass

        f.convertImage(0x01)

        print("Remove finger...")
        time.sleep(2)

        print("Place same finger again...")

        while not f.readImage():
            pass

        f.convertImage(0x02)

        if f.compareCharacteristics() == 0:
            print("Finger mismatch")
            return

        f.createTemplate()

        # Store temporarily in sensor
        position = f.storeTemplate()

        print("Stored at slot:", position)

        # Download fingerprint template
        template = f.downloadCharacteristics(0x01)

        # Convert to base64
        template_bytes = bytes(template)
        template_b64 = base64.b64encode(template_bytes).decode()

        print("\nFingerprint Template (SAVE THIS):\n")
        print(template_b64)

        return template_b64

    except Exception as e:
        print("Error:", e)


enroll_fingerprint()