import React, { useState, useEffect } from 'react';
import { Plus, Play, Edit, Copy, Trash2, Flame, Loader2, Package, Cpu, Terminal, Circle } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import RecipeBuilderModal from './RecipeBuilderModal';

interface RecipesTabProps {
  onBuildTriggered: (buildId: string, recipeName: string) => void;
}

interface ActiveBuildInfo {
  id: string;
  status: string;
}

export default function RecipesTab({ onBuildTriggered }: RecipesTabProps) {
  const { t } = useTranslation();
  const [recipes, setRecipes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeModalRecipe, setActiveModalRecipe] = useState<any | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [triggeringId, setTriggeringId] = useState<number | null>(null);
  const [activeBuildsMap, setActiveBuildsMap] = useState<Record<number, ActiveBuildInfo>>({});

  const fetchActiveBuilds = async () => {
    try {
      const res = await fetch('/api/builds?page=1&size=50');
      if (res.ok) {
        const data = await res.json();
        const map: Record<number, ActiveBuildInfo> = {};
        if (data.items) {
          for (const item of data.items) {
            if (item.status === 'RUNNING' || item.status === 'PENDING') {
              map[item.recipe_id] = { id: item.id, status: item.status };
            }
          }
        }
        setActiveBuildsMap(map);
      }
    } catch (err) {
      console.error('Failed to fetch active builds:', err);
    }
  };

  const fetchRecipes = async () => {
    try {
      const res = await fetch('/api/recipes');
      if (res.ok) {
        setRecipes(await res.json());
      }
    } catch (err) {
      console.error('Failed to fetch recipes:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecipes();
    fetchActiveBuilds();
    const interval = setInterval(() => {
      fetchActiveBuilds();
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  const handleTriggerBuild = async (recipe: any) => {
    setTriggeringId(recipe.id);
    try {
      const res = await fetch(`/api/recipes/${recipe.id}/build`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.build_id) {
        onBuildTriggered(data.build_id, recipe.name);
        fetchRecipes();
      } else {
        alert(data.detail || 'Failed to trigger build');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setTriggeringId(null);
    }
  };

  const handleClone = async (recipeId: number) => {
    try {
      const res = await fetch(`/api/recipes/${recipeId}/clone`, { method: 'POST' });
      if (res.ok) {
        fetchRecipes();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async (recipe: any) => {
    if (window.confirm(t('deleteRecipeConfirm', { name: recipe.name }))) {
      try {
        const res = await fetch(`/api/recipes/${recipe.id}`, { method: 'DELETE' });
        if (res.ok) {
          fetchRecipes();
        }
      } catch (err) {
        console.error(err);
      }
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-5 animate-tab-in">
      {/* Header action bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-xl">
            <Flame size={20} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-zinc-50 tracking-tight">{t('tabRecipes')}</h2>
            <p className="text-[11px] text-zinc-400 font-medium">Configure and execute custom Debian/Ubuntu OS image recipes</p>
          </div>
        </div>

        <button
          onClick={() => {
            setActiveModalRecipe(null);
            setShowModal(true);
          }}
          className="px-3.5 py-1.5 bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs rounded-xl shadow-lg shadow-amber-500/10 transition-all flex items-center gap-1.5 cursor-pointer self-start md:self-auto"
        >
          <Plus size={15} />
          <span>{t('createRecipe')}</span>
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-12 text-zinc-400">
          <Loader2 className="animate-spin mr-2" size={20} />
          <span>Loading image recipes...</span>
        </div>
      ) : recipes.length === 0 ? (
        <div className="p-12 text-center bg-zinc-900 border border-zinc-800 rounded-3xl space-y-4">
          <Package size={40} className="text-zinc-600 mx-auto" />
          <div className="text-sm font-bold text-zinc-300">{t('noRecipes')}</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {recipes.map((recipe) => {
            const activeBuild = activeBuildsMap[recipe.id];
            return (
              <div
                key={recipe.id}
                className={`bg-zinc-900 border rounded-2xl p-5 transition-all duration-200 flex flex-col justify-between space-y-4 shadow-xl group relative ${
                  activeBuild ? 'border-amber-500/50 shadow-amber-500/10 ring-1 ring-amber-500/30' : 'border-zinc-800 hover:border-zinc-700'
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-base font-bold text-zinc-100 group-hover:text-amber-400 transition-colors">
                          {recipe.name}
                        </h3>
                        {activeBuild && (
                          <span className="flex items-center gap-1.5 text-[9px] font-mono font-bold text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded-full animate-pulse">
                            <Circle size={6} className="fill-amber-400 animate-ping" />
                            <span>{activeBuild.status}</span>
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-zinc-400 mt-0.5 line-clamp-2">
                        {recipe.description || 'No description provided.'}
                      </p>
                    </div>
                    <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2.5 py-1 rounded-full font-mono font-bold shrink-0">
                      {recipe.distribution} {recipe.release}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-zinc-400 pt-1">
                    <span className="flex items-center gap-1 bg-zinc-950 px-2 py-1 rounded border border-zinc-800">
                      <Cpu size={12} className="text-zinc-500" />
                      {recipe.architecture}
                    </span>
                    <span className="bg-zinc-950 px-2 py-1 rounded border border-zinc-800">
                      {(recipe.output_formats || []).join(', ')}
                    </span>
                    <span className="bg-zinc-950 px-2 py-1 rounded border border-zinc-800">
                      {(recipe.packages || []).length} pkgs
                    </span>
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="pt-3 border-t border-zinc-800/80 flex items-center justify-between gap-2">
                  {activeBuild ? (
                    <button
                      onClick={() => onBuildTriggered(activeBuild.id, recipe.name)}
                      className="px-3.5 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-zinc-950 font-bold text-xs rounded-xl shadow-lg shadow-amber-500/20 transition-all flex items-center gap-1.5 cursor-pointer animate-pulse"
                      title="Click to view live build console"
                    >
                      <Terminal size={14} />
                      <span>Build Console</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleTriggerBuild(recipe)}
                      disabled={triggeringId === recipe.id}
                      className="px-3.5 py-2 bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs rounded-xl shadow-md transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                    >
                      {triggeringId === recipe.id ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} fill="currentColor" />}
                      <span>{t('buildNow')}</span>
                    </button>
                  )}

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => {
                        setActiveModalRecipe(recipe);
                        setShowModal(true);
                      }}
                      className="p-2 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
                      title={t('editRecipe')}
                    >
                      <Edit size={15} />
                    </button>
                    <button
                      onClick={() => handleClone(recipe.id)}
                      className="p-2 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer"
                      title={t('cloneRecipe')}
                    >
                      <Copy size={15} />
                    </button>
                    <button
                      onClick={() => handleDelete(recipe)}
                      className="p-2 text-zinc-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                      title={t('delete')}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showModal && (
        <RecipeBuilderModal
          recipe={activeModalRecipe}
          onClose={() => setShowModal(false)}
          onSaveSuccess={() => {
            fetchRecipes();
          }}
        />
      )}
    </div>
  );
}
