// Extension points for features outside SkillAlignRAG (for example the FYP's review
// features). This file stays empty on main; another project can fill it in without
// editing the shared components.
//
// overviewColumns: [{ key, header, render: (row) => node }]   extra columns in the matrix
// drawerSections:  [(detail) => node | null]                  extra sections in the evidence drawer
// pages:           [{ key, label, render: (props) => node }]  extra navigation pages; props.title is
//                                                             the label, for the page's <PageHeader> (components/ui.jsx)
export const overviewColumns = [];
export const drawerSections = [];
export const pages = [];
