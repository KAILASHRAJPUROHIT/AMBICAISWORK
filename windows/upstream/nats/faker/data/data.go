package data

import (
	"fmt"
	"math/rand"
	"strings"
	"time"

	"github.com/brianvoe/gofakeit/v7"
	"github.com/open-uem/nats"
)

var ComputerNames = []string{"MINASTIRITH", "EDORAS", "GONDOLIN", "ISENGARD", "MORIA", "HOBITTON", "FANGORN", "BREE", "PELARGIR", "EREBOR", "GONDOR", "DOLAMROTH", "AMROTH", "OSGILIATH", "BELERIAND", "MINASMORGUL", "BELEGOST", "CIRITHUNGOL"}

var UIDs = []string{"e45c2ac2-afc4-48b9-8835-fd6b8125c1d4", "ac743250-c2f8-422c-b9a1-cae73b2e6613", "5563c560-4a83-427d-85c2-e012ff5c9b5c", "48f5ee7f-3324-4a19-9274-af7a80f7b76a", "3e687326-de7c-4e81-a5b7-4b25a2137d22", "e3670df0-a2dd-420c-9584-2eaba894eb1a", "66a34625-2b37-4537-9105-77f10243b86c", "da8bd5f3-1ac7-4eee-a8ea-3d2feab2cf40", "be1c50af-3cec-4412-a947-a2d2a3dafa67", "8ea391bc-64a2-4c91-bdfe-5f350c7006b2", "f84ba6a4-5ee9-4693-ae97-a566bbf89d5e", "aafd0f08-f493-493c-b1c1-ec2bcc734ef6", "30121045-38ee-479a-9a2c-db4aa435d88b", "164728ce-0a6c-4d86-85ad-89241c16e2e0", "0a44ff06-b409-463c-9f07-91449522fe5f", "2386cc15-3247-464c-9c44-7f74d1fa3c50", "aed8ee8f-148c-4e4c-8e93-f7d5edb814ec", "06dc28fe-10a7-4cf0-ba07-562941d5d635", "b5bb7d4d-67c4-495c-a98b-a3b9cf7ce6c8"}
var MACs = []string{"CB-FC-EC-2D-FE-3C", "BA-E3-FB-8B-CE-B7", "EE-6F-BE-0F-E0-BB", "DA-9A-FE-94-BE-F5", "A0-ED-EB-76-46-D2", "BF-BB-9B-88-C1-11", "1C-C5-20-DA-DC-78", "D1-26-5C-A7-2B-7A", "16-B5-BC-4D-E4-ED", "FE-99-D6-A7-EC-88", "DF-D6-B7-35-2C-DD", "A7-D1-C9-A9-97-3F", "6E-20-19-93-5A-FF", "DE-BE-D9-FC-BD-B3", "EE-B4-99-F5-E2-1C", "2B-DB-A8-8C-AB-39", "A2-BC-B6-3C-E3-CD", "9E-1D-EF-86-A6-EA"}
var MemorySizes = []int{4096, 8192, 16384, 20480, 32768}
var VNCs = []string{"", "UltraVNC", "TightVNC", "TigerVNC"}
var Manufacturers = []string{"HP", "Lenovo", "Dell", "ASUS"}
var Processors = []string{"AMD Ryzen 5 7520U", "Intel Core i7-14700F", "Intel Core i3-1315U", "AMD Ryzen 3 7320", "AMD Ryzen5 5600G"}
var SerialNumbers = []string{"GFQ5PQ75E22RXWAUXJP3", "XJ8L73R4Q6XEQE8EJ2SB", "Y2QJW7A32TQ2EHRGFCAH", "BZU97JAPN57JHKCR5XYE", "S8DPHM2DVVSY9SGP4HCL", "HMZKRY9MQ9QSWAVKWGUJ", "3UFSXPM9ADZE7CSQHER7", "B7PJTPC66H9PDKBNFFNT", "ZJBA9CV794CDBLV5PC2K", "H3V7X6PJPCP935YSDWDT", "C9DGNM9N7R4LDAYD5KMJ", "2NPBUXW98DY3NJV7TH7N", "ZJ4GWMUQWX6PXJGFV3JH", "YESCYTM2VMU52RUQNLQS", "DULCV7E6SDL6AFUW8GTG", "4MNK55AMRLBWWZX6SKLJ", "L4YKVD9Z7AG4M2YX38Q2", "6482QKUHQ2LDCMT2YKC6"}
var NProcessors = []int{2, 4, 8}
var WindowsVersions = []string{"Windows 11 23H2", "Windows 11 22H2", "Windows 11 21H2", "Windows 10 22H2", "Windows 10 21H2", "Windows 10 21H1"}
var Antivirus = []string{"Sophos Intercept X", "Windows Defender", "CrowdStrike Falcon Endpoint Protection", "ESET Protect", "Symantec End-user Endpoint Security"}
var Users = []string{}
var LastSearchTimes = []time.Time{time.Now(), time.Time.Add(time.Now(), -48*time.Hour), time.Time.Add(time.Now(), -20*time.Hour), time.Time.Add(time.Now(), -32*time.Hour)}
var LastInstallTimes = []time.Time{time.Now(), time.Time.Add(time.Now(), -90*time.Hour), time.Time.Add(time.Now(), -65*time.Hour), time.Time.Add(time.Now(), -52*time.Hour)}

func GetModel(manufacturer string) string {
	var Models = make(map[string][]string, len(Manufacturers))
	Models["HP"] = []string{"ProDesk 600 G5", "EliteDesk 800 G9"}
	Models["Dell"] = []string{"Optiplex 7020", "Precision 3660"}
	Models["Lenovo"] = []string{"ThinkCentre M75q", "ThinkPad E16 Gen6"}
	Models["ASUS"] = []string{"ExpertBook B1", "VivoBook Pro 15"}

	return Models[manufacturer][rand.Intn(len(Models[manufacturer]))]
}

func GetWindowsOSDescription(os string) string {
	if strings.Contains(os, "Windows 11") {
		return "Microsoft Windows 11 Pro"
	} else {
		return "Microsoft Windows 10 Pro"
	}
}

func GetFakeAgent(index int) nats.AgentReport {
	faker := gofakeit.New(0)
	updateStatus := nats.SystemUpdatePossibleStatus()

	report := nats.AgentReport{}
	report.AgentID = UIDs[index]
	report.OS = "windows"
	report.Hostname = ComputerNames[index]
	report.Release = nats.Release{
		Version: "0.1.0",
		Channel: "stable",
		Arch:    "amd64",
		Os:      "windows",
	}

	if releaseDate, err := time.Parse("2006-01-02", "2024-11-20"); err == nil {
		report.Release.ReleaseDate = releaseDate
	}

	report.VNCProxyPort = "1443"
	report.SFTPPort = "2022"
	report.IP = fmt.Sprintf("192.168.1.%d", 60+index)
	report.MACAddress = MACs[index]
	report.SupportedVNCServer = VNCs[rand.Intn(len(VNCs))]
	report.Computer.Manufacturer = Manufacturers[rand.Intn(len(Manufacturers))]
	report.Computer.Serial = SerialNumbers[rand.Intn(len(SerialNumbers))]
	report.Computer.Model = GetModel(report.Computer.Manufacturer)
	report.Computer.Memory = uint64(MemorySizes[rand.Intn(len(MemorySizes))])
	report.Computer.Processor = Processors[rand.Intn(len(Processors))]
	report.Computer.ProcessorCores = int64(NProcessors[rand.Intn(len(NProcessors))])
	report.Computer.ProcessorArch = "x64"
	report.OperatingSystem.Username = report.Hostname + "\\" + faker.Username()
	report.OperatingSystem.Version = WindowsVersions[rand.Intn(len(WindowsVersions))]
	report.OperatingSystem.Description = GetWindowsOSDescription(report.OperatingSystem.Version)
	report.OperatingSystem.Arch = "64 bits"
	report.OperatingSystem.InstallDate = time.Time.Add(time.Now(), -365*2*24*time.Hour)
	report.OperatingSystem.LastBootUpTime = time.Time.Add(time.Now(), -3*time.Hour)
	report.OperatingSystem.Edition = "Professional"
	report.Antivirus.Name = Antivirus[rand.Intn(len(Antivirus))]
	report.Antivirus.IsActive = rand.Intn(2) == 1
	report.Antivirus.IsUpdated = rand.Intn(2) == 1
	report.SystemUpdate.Status = updateStatus[rand.Intn(len(updateStatus))]
	report.SystemUpdate.PendingUpdates = rand.Intn(2) == 1
	report.SystemUpdate.LastInstall = LastInstallTimes[rand.Intn(len(LastInstallTimes))]
	report.SystemUpdate.LastSearch = LastSearchTimes[rand.Intn(len(LastSearchTimes))]
	return report
}
