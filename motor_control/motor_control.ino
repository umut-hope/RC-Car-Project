const int IN1 = 5;
const int IN2 = 6;
const int IN3 = 7;
const int IN4 = 8;

void setup() {
  Serial.begin(115200);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopCar();
  Serial.println("[OK] Arduino ready.");
}

void forward()   { digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW);  digitalWrite(IN3,HIGH); digitalWrite(IN4,LOW);  }
void backward()  { digitalWrite(IN1,LOW);  digitalWrite(IN2,HIGH); digitalWrite(IN3,LOW);  digitalWrite(IN4,HIGH); }
void turnLeft()  { digitalWrite(IN1,LOW);  digitalWrite(IN2,HIGH); digitalWrite(IN3,HIGH); digitalWrite(IN4,LOW);  }
void turnRight() { digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW);  digitalWrite(IN3,LOW);  digitalWrite(IN4,HIGH); }
void stopCar()   { digitalWrite(IN1,LOW);  digitalWrite(IN2,LOW);  digitalWrite(IN3,LOW);  digitalWrite(IN4,LOW);  }

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() == 0) return;

    if      (cmd.startsWith("F"))      { forward();   Serial.println("[CMD] FORWARD");  }
    else if (cmd.startsWith("B"))      { backward();  Serial.println("[CMD] BACKWARD"); }
    else if (cmd.startsWith("L_TURN")) { turnLeft();  Serial.println("[CMD] LEFT");     }
    else if (cmd.startsWith("R_TURN")) { turnRight(); Serial.println("[CMD] RIGHT");    }
    else if (cmd.startsWith("H"))      { stopCar();   Serial.println("[CMD] STOP");     }
    else { Serial.print("[UNKNOWN] "); Serial.println(cmd); }
  }
}
