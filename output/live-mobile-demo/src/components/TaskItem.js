import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';

export default function TaskItem({ task, onToggleComplete, onDelete }) {
  return (
    <View style={[styles.container, task.completed && styles.completedContainer]}>
      <TouchableOpacity 
        style={styles.checkboxContainer} 
        onPress={() => onToggleComplete(task.id)}
      >
        <View style={[styles.checkbox, task.completed && styles.checkedBox]}>
          {task.completed && <Text style={styles.checkmark}>✓</Text>}
        </View>
      </TouchableOpacity>
      
      <View style={styles.textContainer}>
        <Text style={[styles.title, task.completed && styles.completedTitle]}>
          {task.title}
        </Text>
        {task.description ? (
          <Text style={[styles.description, task.completed && styles.completedDescription]}>
            {task.description}
          </Text>
        ) : null}
      </View>

      <TouchableOpacity 
        style={styles.deleteButton} 
        onPress={() => onDelete(task.id)}
      >
        <Text style={styles.deleteText}>✕</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    padding: 14,
    borderRadius: 10,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  completedContainer: {
    backgroundColor: '#f8f9fa',
    opacity: 0.8,
  },
  checkboxContainer: {
    marginRight: 12,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 2,
    borderColor: '#007AFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkedBox: {
    backgroundColor: '#007AFF',
  },
  checkmark: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: 'bold',
  },
  textContainer: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    color: '#333333',
    fontWeight: '500',
  },
  completedTitle: {
    textDecorationLine: 'line-through',
    color: '#8e8e93',
  },
  description: {
    fontSize: 13,
    color: '#666666',
    marginTop: 2,
  },
  completedDescription: {
    textDecorationLine: 'line-through',
    color: '#aeaeb2',
  },
  deleteButton: {
    padding: 6,
  },
  deleteText: {
    fontSize: 16,
    color: '#ff3b30',
    fontWeight: 'bold',
  },
});
