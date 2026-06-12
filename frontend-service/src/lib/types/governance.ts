export interface Tag {
  id: string;
  label: string;
  color?: 'slate'|'blue'|'cyan'|'emerald'|'amber'|'rose'|'purple';
}

export interface Guardian {
  id: string;
  display_name: string;
  role: 'guardian';
}
