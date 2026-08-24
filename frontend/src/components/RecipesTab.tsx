import React, { useState, useEffect } from 'react';
import { Plus, Play, Edit, Copy, Trash2, Flame, Loader2, Package, Cpu, Terminal, Circle, XCircle, FlaskConical, MemoryStick } from 'lucide-react';
import { useTranslation } from '../context/TranslationContext';
import RecipeBuilderModal from './RecipeBuilderModal';
import { BOARDS } from './BoardSelector';

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
      const res = await fetch('/api/builds?page=1&limit=50');
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

  const handleCancelBuild = async (buildId: string) => {
    try {
      const res = await fetch(`/api/builds/${buildId}/cancel`, { method: 'POST' });
      if (res.ok) {
        fetchActiveBuilds();
        fetchRecipes();
      }
    } catch (err) {
      console.error(err);
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
    <div className="space-y-6 animate-tab-in">
      {/* Header action bar */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-zinc-50">{t('tabRecipes')}</h2>
          <p className="text-sm text-zinc-400">{t('recipesSubtitle')}</p>
        </div>

        <button
          onClick={() => {
            setActiveModalRecipe(null);
            setShowModal(true);
          }}
          className="px-3.5 py-2 bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs rounded-xl shadow-lg shadow-amber-500/10 transition-all flex items-center gap-1.5 cursor-pointer self-start sm:self-auto"
        >
          <Plus size={15} />
          <span>{t('createRecipe')}</span>
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-12 text-zinc-400">
          <Loader2 className="animate-spin mr-2" size={20} />
          <span>{t('loadingBuildHistory')}</span>
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
                  activeBuild
                    ? 'border-amber-500/50 shadow-amber-500/10 ring-1 ring-amber-500/30'
                    : recipe.is_dev
                    ? 'border-fuchsia-500/40 shadow-fuchsia-950/20 ring-1 ring-fuchsia-500/20'
                    : 'border-zinc-800 hover:border-zinc-700'
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <h3 title={recipe.name} className="text-base font-bold text-zinc-100 group-hover:text-amber-400 transition-colors truncate min-w-0">
                      {recipe.name}
                    </h3>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {recipe.is_dev && (
                        <span
                          title={t('devBuildHint') || 'Marks this recipe as a dev build. Artifacts are named edge-dev_… so dev images cannot be confused with release ones.'}
                          className="flex items-center gap-1 text-[9px] font-mono font-bold text-fuchsia-400 bg-fuchsia-500/10 border border-fuchsia-500/30 px-2 py-0.5 rounded-full"
                        >
                          <FlaskConical size={10} />
                          <span>{t('devBadge') || 'DEV'}</span>
                        </span>
                      )}
                      {activeBuild && (
                        <span className="flex items-center gap-1.5 text-[9px] font-mono font-bold text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded-full animate-pulse">
                          <Circle size={6} className="fill-amber-400 animate-ping" />
                          <span>{activeBuild.status}</span>
                        </span>
                      )}
                    </div>
                  </div>

                  <p className="text-xs text-zinc-400 line-clamp-2 min-h-[2rem]">
                    {recipe.description || t('noDescription')}
                  </p>

                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono pt-1">
                    <span className="bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2.5 py-1 rounded-lg font-bold">
                      {recipe.distribution} {recipe.release}
                    </span>
                    <span className="flex items-center gap-1 bg-zinc-950 text-zinc-400 px-2.5 py-1 rounded-lg border border-zinc-800">
                      <Cpu size={12} className="text-zinc-500" />
                      {recipe.architecture}
                    </span>
                    {recipe.distribution === 'armbian' && (
                      <span className="flex items-center gap-1 bg-zinc-950 text-zinc-400 px-2.5 py-1 rounded-lg border border-zinc-800">
                        <MemoryStick size={12} className="text-zinc-500" />
                        {BOARDS.find((b) => b.id === recipe.board)?.name || recipe.board}
                      </span>
                    )}
                    <span className="bg-zinc-950 text-zinc-400 px-2.5 py-1 rounded-lg border border-zinc-800">
                      {(recipe.output_formats || []).join(', ')}
                    </span>
                    <span className="bg-zinc-950 text-zinc-400 px-2.5 py-1 rounded-lg border border-zinc-800">
                      {(recipe.packages || []).length} pkgs
                    </span>
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="pt-3 border-t border-zinc-800/80 flex items-center justify-between gap-2">
                  {activeBuild ? (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => onBuildTriggered(activeBuild.id, recipe.name)}
                        className="px-3.5 py-2 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-zinc-950 font-bold text-xs rounded-xl shadow-lg shadow-amber-500/20 transition-all flex items-center gap-1.5 cursor-pointer animate-pulse"
                        title="Click to view live build console"
                      >
                        <Terminal size={14} />
                        <span>Build Console</span>
                      </button>
                      <button
                        onClick={() => handleCancelBuild(activeBuild.id)}
                        className="p-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 rounded-xl transition-colors cursor-pointer flex items-center gap-1 text-xs font-bold"
                        title={t('cancelBuild')}
                      >
                        <XCircle size={15} />
                      </button>
                    </div>
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
