import time

BAUD=115200
LOG_NAMES={"/environment.csv","/sessions.csv","/bme688_iaq_log.csv","/bme688_full_log.csv"}
def is_log(path): return path in LOG_NAMES or (path.startswith("/cap_") and path.endswith(".bmerawdata"))

def likely_port():
    try:
        from serial.tools import list_ports
        ports=list(list_ports.comports())
    except ImportError: return None
    for port in ports:
        if any(x in f"{port.description} {port.manufacturer} {port.hwid}".lower() for x in ("cp210","ch340","usb serial","silicon labs","esp32")): return port.device
    return ports[0].device if ports else None

class Device:
    def __init__(self,port):
        import serial
        self.port=port; self.serial=serial.Serial(port,BAUD,timeout=.25); time.sleep(2); self.serial.reset_input_buffer()
    def close(self): self.serial.close()
    def send(self,command): self.serial.write((command+"\n").encode()); self.serial.flush()
    def command(self,command,seconds=2):
        self.send(command); result=[]; deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            raw=self.serial.readline()
            if raw: result.append(raw.decode(errors="replace").strip())
        return result
    def identify(self):
        text="\n".join(self.command("STATUS"))
        if not any(x in text.upper() for x in ("MOLDSENSE","MODE=","BSEC")): raise RuntimeError("Serial device is not compatible MoldSense firmware.")
        return text
    def list_files(self):
        self.send("FILES"); lines=[]; deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            raw=self.serial.readline()
            if raw:
                line=raw.decode(errors="replace").strip(); lines.append(line)
                if line=="-----FILES_END-----": break
        else: raise TimeoutError("Device did not finish listing files")
        found=[]; inside=False
        for line in lines:
            if line=="-----FILES_BEGIN-----": inside=True
            elif inside and line!="-----FILES_END-----" and "," in line:
                name,size=line.rsplit(",",1)
                try: found.append((name if name.startswith("/") else "/"+name,int(size)))
                except ValueError: pass
        return found
    def download(self,path,timeout=180):
        self.send(f"FILE_DUMP {path}"); chunks=[]; collecting=False; deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            raw=self.serial.readline()
            if not raw: continue
            line=raw.decode("ascii",errors="ignore").strip()
            if line=="-----FILE_HEX_BEGIN-----": collecting=True
            elif line=="-----FILE_HEX_END-----": return bytes.fromhex("".join(chunks))
            elif line=="FILE_NOT_FOUND": raise FileNotFoundError(path)
            elif collecting: chunks.append(line)
        raise TimeoutError(f"Download timed out: {path}")
    def delete_log(self,path):
        if not is_log(path): raise ValueError("Refusing to delete protected or unknown file")
        if "LOG_DELETED" not in self.command(f"LOG_DELETE {path}"): raise RuntimeError("Firmware lacks safe log deletion. Archive kept; install the included firmware extension before clearing storage.")
