import { useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "tiptap-markdown";

const PLACEHOLDER =
  "Describa las reglas de negocio a considerar: validaciones, criterios de transformación, condiciones especiales, etc.";

export default function BusinessRulesEditor({ value, onChange }) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown,
      Placeholder.configure({ placeholder: PLACEHOLDER }),
    ],
    content: value,
    onUpdate: ({ editor }) => {
      onChange(editor.storage.markdown.getMarkdown());
    },
  });

  // Sync value when changed externally (e.g. "Cargar Ejemplo" resets parent state)
  useEffect(() => {
    if (!editor) return;
    const current = editor.storage.markdown.getMarkdown();
    if (current !== value) {
      editor.commands.setContent(value ?? "", false);
    }
  }, [value, editor]);

  return <EditorContent editor={editor} className="br-editor" />;
}
