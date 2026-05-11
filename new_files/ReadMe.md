Das "Script_Read_Scale.py" dient der Steuerung der Waage
 
Ziel ist das kontinuierliche auslesen alle X Sekunden (default=5s). Besonders wichtig ist, dass das Gewicht initial (also bevor die Pumpe aktiviert ist) einmal gespeichert wird.

Gewichte sollten je run mit timestamp und in eine Datei wie die zum log der pumpe gespeichert werden (ggf. auch in die gleiche)



Das Programm "Function_generator.py" ist zur Kontrolle von Schwingungsfrequenz und Amplitude. 

Im Experiment.yaml sollte man neben den verschiedenen Drehzahlen der Pumpe jetzt auch verschiedene Frequenzen, sowie Spannungsamplituden angeben können, die dann abgefahren werden.

Wichtig ist, dass der Typ der Frequenz eine Sinusschwingung ist und die Amplitude als peak-to-Peak angegeben wird (kann seriell an das Gerät weitergegeben werden)

Als Limit der Amplitude sollte 9.5V hinterlegt werden, da es bei höheren Spannungen zu Beschädigungen kommen könnte.

Beispiel:

   Drehzahlen/Flussraten: 200, 800, 1000
   Frequenzen (Hz): 20, 25, 30
   Amplituden (V): 3, 5, 9

Dann sollte das Programm zuerst bei konstanter Drehzahl und Frequenz alle Amplituden durchprobieren, dann bei gleicher Drehzahl bei der 2. Frequenz alle Amplituden ausprobieren usw. Die Drehzahl sollte also quasi als höchster Parameter in der Hierarchie betrachtet werden


Insgesamt ist es wichtig, dass bei den gespeicherten Bilder nachvollziehbar ist, welche Bilder bei welchen Parametern gemacht wurde. (Evtl. je Kombination ein Ordner)



**TO DO:**
- Oscilloscope.csv etc. für jeden Run in Sub-Folder abspeichern, sodass rohdaten dem jeweiligen Step zugeordnet werden können.

- Jeden einzelnen Run mit Timestamp indexen und in Batch Report Datei hinterlegen, sodass nach einzelnen Parametern gefiltert werden kann ("Zeige mir alle Runs mit Material X und der Kombination aus FlowRate Y und Frequenz Z")
