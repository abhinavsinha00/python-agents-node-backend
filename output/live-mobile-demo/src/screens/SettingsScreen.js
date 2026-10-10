import React, { useState, useEffect } from 'react';
import { View, Text, Switch, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import { loadSettings, saveSettings, saveTasks } from '../storage/taskStorage';

export default function SettingsScreen({ navigation }) {
  const [settings, setSettings] = useState({ theme: 'light', soundEnabled: true });

  useEffect(() => {
    loadSettings().then(setSettings);
  }, []);

  const handleToggleSound = async () => {
    const updated = { ...settings, soundEnabled: !settings.soundEnabled };
    setSettings(updated);
    await saveSettings(updated);
  };

  const handleClearAll = () => {
    Alert.alert(
      'Clear All Tasks',
      'Are you sure you want to delete all your tasks? This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Delete All', 
          style: 'destructive',
          onPress: async () => {
            await saveTasks([]);
            Alert.alert('Success', 'All tasks have been cleared.');
          }
        }
      ]
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Text style={styles.backButtonText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={{ width: 50 }} />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Preferences</Text>
        
        <View style={styles.settingRow}>
          <Text style={styles.settingLabel}>Sound Effects</Text>
          <Switch 
            value={settings.soundEnabled}
            onValueChange={handleToggleSound}
          />
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Data Management</Text>
        
        <TouchableOpacity style={styles.dangerButton} onPress={handleClearAll}>
          <Text style={styles.dangerButtonText}>Clear All Tasks</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.aboutSection}>
        <Text style={styles.aboutText}>Live Mobile Todo App v1.0.0</Text>
        <Text style={styles.aboutSubText}>Built with React Native & Expo</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 60,
    paddingBottom: 15,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e5e5ea',
  },
  backButton: {
    paddingVertical: 4,
  },
  backButtonText: {
    fontSize: 16,
    color: '#007AFF',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#000000',
  },
  section: {
    marginTop: 20,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: '#e5e5ea',
    paddingVertical: 4,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6d6d72',
    textTransform: 'uppercase',
    paddingHorizontal: 20,
    paddingVertical: 8,
  },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderTopWidth: 1,
    borderTopColor: '#f2f2f7',
  },
  settingLabel: {
    fontSize: 16,
    color: '#000000',
  },
  dangerButton: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderTopWidth: 1,
    borderTopColor: '#f2f2f7',
  },
  dangerButtonText: {
    fontSize: 16,
    color: '#ff3b30',
    fontWeight: '500',
  },
  aboutSection: {
    marginTop: 40,
    alignItems: 'center',
  },
  aboutText: {
    fontSize: 14,
    color: '#8e8e93',
    fontWeight: '500',
  },
  aboutSubText: {
    fontSize: 12,
    color: '#aeaeb2',
    marginTop: 4,
  },
});
